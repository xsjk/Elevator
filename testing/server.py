import asyncio
import logging

from aioconsole import ainput
from .common import Server, message_sender
from .passenger import generate_passengers  # import Passenger for annotation and factory

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Set logging level to INFO for better visibility

#######   ELEVATOR PROJECT    #######


async def testing(
    server: Server,
    client_addr: str,
    num: int | None = None,
    request_queue: asyncio.Queue | None = None,
) -> bool:
    """Run elevator testing with generated or injected passengers

    Args:
        server: Server instance
        client_addr: Client address to test
        num: Number of passengers (interactive if None)
        request_queue: Existing queue or None to create new one

    Returns:
        True if test completed successfully
    """
    # Determine number of passengers (interactive if not provided)
    if num is None:
        while True:
            try:
                num = int(await ainput("Enter passenger count (>0): "))
                if num > 0:
                    break
                logger.warning("Number must be positive")
            except ValueError:
                logger.warning("Invalid number")

    # Initialize queue and passenger list
    queue = request_queue if request_queue is not None else asyncio.Queue()
    passengers = generate_passengers(num, queue)

    logger.info(f"Created {len(passengers)} passengers:")
    for p in passengers:
        logger.info(f"  {p}")

    # Verify client connection
    if not server.clients_addr:
        logger.error("No clients connected!")
        return False

    # Use provided client_addr or verify it exists in clients_addr
    if client_addr not in server.clients_addr:
        logger.warning(f"Specified client {client_addr} not connected, using first available client")
        client_addr = list(server.clients_addr)[0]

    logger.info(f"Testing with client: {client_addr}")

    # Reset elevator system
    await server.send(client_addr, "reset")
    await asyncio.sleep(1)

    # Start message sender task
    sender_task = asyncio.create_task(message_sender(server, client_addr, queue))

    # Track progress
    completed = 0
    active = set(passengers)

    # Main processing loop
    async for address, message, _ in server.messages():
        if address != client_addr:
            continue

        # Process message for each active passenger
        for passenger in list(active):
            if passenger.handle_message(message):
                completed += 1
                active.remove(passenger)

        # Test completion check
        if completed == len(passengers):
            logger.info("TEST PASSED: All passengers reached destinations!")
            await asyncio.sleep(1)
            await server.send(client_addr, "reset")
            if address in server.clients_addr:
                server.clients_addr.remove(address)
            break

    sender_task.cancel()
    try:
        await sender_task
    except asyncio.CancelledError:
        pass
    logger.info("Test completed")
    return True


async def main():
    server = Server()
    server.start()
    logger.info("Server started. Waiting for clients...")
    try:
        while True:
            try:
                addr = await server.get_next_client()
                logger.info(f"Client connected: {addr}")
                user_input = await ainput(f"Start testing for {addr}? (y/n)\n")
                if user_input.lower() == "y":
                    await testing(server, addr)
            except Exception as e:
                logger.error(f"Error: {e}")

    except asyncio.CancelledError:
        logger.info("Server shutdown requested")
    finally:
        server.stop()
        logger.info("Server stopped")


if __name__ == "__main__":
    asyncio.run(main())
