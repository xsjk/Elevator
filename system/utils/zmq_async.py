import argparse
import asyncio
import inspect
import logging
import time
from abc import ABC, abstractmethod
from typing import AsyncGenerator

import zmq
import zmq.asyncio
from rich.logging import RichHandler

logging.basicConfig(
    level="INFO",
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler()],
)
logger = logging.getLogger(__name__)


class Base(ABC):
    def __init__(self):
        self._context = zmq.asyncio.Context()
        self._socket: zmq.asyncio.Socket | None = None

        self._send_queue = asyncio.Queue()
        self._receive_queue = asyncio.Queue()

    def __del__(self):
        if self._socket is not None:
            self._socket.setsockopt(zmq.LINGER, 0)

    @property
    def socket(self):
        if self._socket is None:
            raise RuntimeError("Socket is not initialized")
        return self._socket

    @socket.setter
    def socket(self, value: zmq.asyncio.Socket):
        if not isinstance(value, zmq.asyncio.Socket):
            raise TypeError("Socket must be an instance of zmq.asyncio.Socket")
        self._socket = value

    def start(self, tg: asyncio.TaskGroup | None = None) -> None:
        e = asyncio if tg is None else tg
        self._listen_task = e.create_task(self._listen_for_messages(), name=f"{self.__class__.__name__}ListenTask {__file__}:{inspect.stack()[0].lineno}")
        self._send_task = e.create_task(self._process_send_queue(), name=f"{self.__class__.__name__}SendTask {__file__}:{inspect.stack()[0].lineno}")

    def stop(self) -> None:
        if self._listen_task:
            self._listen_task.cancel()
        if self._send_task:
            self._send_task.cancel()

    @abstractmethod
    async def send(self, *args, **kwargs) -> None:
        pass

    @abstractmethod
    async def read(self) -> tuple:
        pass

    @abstractmethod
    async def _listen_for_messages(self):
        pass

    @abstractmethod
    async def _process_send_queue(self):
        pass


class Client(Base):
    def __init__(self, server_host="127.0.0.1", port=27132, identity="GroupX"):
        super().__init__()

        self.socket = self._context.socket(zmq.DEALER)
        self.socket.setsockopt_string(zmq.IDENTITY, identity)
        self.socket.connect(f"tcp://{server_host}:{port}")
        logger.debug(f"Client connected to {server_host}:{port}, identity: {identity}")

    @property
    def identity(self):
        return self.socket.getsockopt_string(zmq.IDENTITY)

    async def send(self, data):
        await self._send_queue.put(data)

    async def read(self):
        message, timestamp = await self._receive_queue.get()
        self._receive_queue.task_done()
        return message, timestamp

    async def messages(self) -> AsyncGenerator[tuple[str, int], None]:
        while True:
            message, timestamp = await self.read()
            yield message, timestamp

    async def _listen_for_messages(self):
        try:
            while True:
                message = await self.socket.recv()
                message_str = message.decode()

                timestamp = int(round(time.time() * 1000))
                await self._receive_queue.put((message_str, timestamp))
                logger.debug(f'Server -> Client[{self.identity}]: "{message_str}"')
        except asyncio.CancelledError:
            pass

    async def _process_send_queue(self):
        try:
            while True:
                message = await self._send_queue.get()
                self._send_queue.task_done()
                await self.socket.send_string(message)
                logger.debug(f'Client[{self.identity}] -> Server: "{message}"')
        except asyncio.CancelledError:
            pass


class Server(Base):
    def __init__(self, server_host="127.0.0.1", server_port=27132):
        super().__init__()
        self.clients_addr = set()
        self.client_queue = asyncio.Queue(maxsize=100)

        self.socket = self._context.socket(zmq.ROUTER)
        self.socket.bind(f"tcp://{server_host}:{server_port}")
        logger.debug(f"Server listening on port: {server_port}")

    async def get_next_client(self):
        return await self.client_queue.get()

    async def send(self, address, data):
        await self._send_queue.put((address, data))

    async def read(self):
        address, message, timestamp = await self._receive_queue.get()
        self._receive_queue.task_done()
        return address, message, timestamp

    async def messages(self) -> AsyncGenerator[tuple[str, str, int], None]:
        while True:
            address, message, timestamp = await self.read()
            yield address, message, timestamp

    async def _listen_for_messages(self):
        try:
            while True:
                address, message = await self.socket.recv_multipart()
                address = address.decode()
                message = message.decode()

                if address not in self.clients_addr:
                    self.clients_addr.add(address)
                    await self.client_queue.put(address)

                timestamp = int(round(time.time() * 1000))
                await self._receive_queue.put((address, message, timestamp))

                logger.debug(f'Client[{address}] -> Server: "{message}"')
        except asyncio.CancelledError:
            pass

    async def _process_send_queue(self):
        try:
            while True:
                address, data = await self._send_queue.get()
                self._send_queue.task_done()
                await self.socket.send_multipart([address.encode(), data.encode()])

                logger.debug(f'Server -> Client[{address}]: "{data}"')
        except asyncio.CancelledError:
            pass


if __name__ == "__main__":

    async def main():
        parser = argparse.ArgumentParser(description="ZMQ Async Server/Client")
        parser.add_argument("mode", choices=["server", "client"], help="Run in server or client mode")
        parser.add_argument("--ip", default="127.0.0.1", help="Server IP address")
        parser.add_argument("--port", type=int, default=27132, help="Port number")
        parser.add_argument("--identity", default="ClientX", help="Client identity (client mode)")

        args = parser.parse_args()

        try:
            match args.mode:
                case "server":
                    server = Server(server_host=args.ip, server_port=args.port)

                    async def message_echo_loop():
                        async for address, message, _ in server.messages():
                            logger.info(f"Message received from {address}: {message}")
                            await server.send(address, f"Echo: {message}")

                    server.start()
                    await message_echo_loop()

                case "client":
                    client = Client(server_host=args.ip, port=args.port, identity=args.identity)

                    async def process_client_messages():
                        async for message, _ in client.messages():
                            logger.info(f"Response received: {message}")

                    async def send_messages():
                        for i in range(5):
                            message = f"Greeting from {args.identity} {i + 1}"
                            await client.send(message)
                            logger.info(f"Message sent: {message}")
                            await asyncio.sleep(1)

                    client.start()
                    await asyncio.gather(process_client_messages(), send_messages())

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error: {e}")

    asyncio.run(main())
