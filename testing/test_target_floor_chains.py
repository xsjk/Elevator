import unittest

from common import Direction, FloorAction, TargetFloorChains


class TestTargetFloorChains(unittest.TestCase):
    def setUp(self):
        self.chains = TargetFloorChains()

    def testdirection(self):
        self.chains.direction = Direction.UP
        self.assertEqual(self.chains.current_chain.direction, Direction.UP)
        self.assertEqual(self.chains.next_chain.direction, Direction.DOWN)
        self.assertEqual(self.chains.future_chain.direction, Direction.UP)

    def test_swap_and_pop(self):
        # TestCase 1:
        with self.assertRaises(IndexError):
            self.chains.pop()

        # TestCase of _swap_chains()
        # TestCase 2 of pop():
        self.chains.direction = Direction.UP
        self.chains.next_chain.add(2, Direction.DOWN)
        result_1 = self.chains.pop()
        self.assertEqual(self.chains.current_chain.direction, Direction.IDLE)
        self.assertEqual(result_1, FloorAction(2, Direction.DOWN))

        # TestCase 3
        self.chains.direction = Direction.DOWN
        self.chains.current_chain.add(3, Direction.DOWN)
        result_2 = self.chains.pop()
        self.assertEqual(result_2, FloorAction(3, Direction.DOWN))

        # TestCase 4
        self.chains.direction = Direction.IDLE
        self.chains.current_chain.add(3, Direction.IDLE)
        self.chains.current_chain.add(2, Direction.IDLE)
        self.chains.next_chain.add(1, Direction.IDLE)
        result_3 = self.chains.pop()
        self.assertEqual(result_3, FloorAction(2, Direction.IDLE))

        # TestCase 5
        result_4 = self.chains.pop()
        self.assertEqual(result_4, FloorAction(3, Direction.IDLE))
        self.assertEqual(self.chains.current_chain, [FloorAction(1, Direction.IDLE)])
        self.assertEqual(len(self.chains.next_chain), 0)
        self.assertEqual(len(self.chains.future_chain), 0)

        # TestCase 6
        result_5 = self.chains.pop()
        self.assertEqual(result_5, FloorAction(1, Direction.IDLE))
        self.assertEqual(len(self.chains), 0)

    def test_top(self):
        self.chains.direction = Direction.UP
        self.chains.future_chain.add(3, Direction.UP)
        self.assertEqual(self.chains.top(), FloorAction(3, Direction.UP))

    def test_remove(self):
        self.chains.direction = Direction.UP
        a1 = FloorAction(1, Direction.UP)
        a4 = FloorAction(2, Direction.UP)
        a2 = FloorAction(2, Direction.DOWN)
        a5 = FloorAction(3, Direction.DOWN)
        a3 = FloorAction(3, Direction.UP)
        self.chains.current_chain.add(1, Direction.UP)
        self.chains.current_chain.add(2, Direction.UP)
        self.chains.next_chain.add(2, Direction.DOWN)
        self.chains.next_chain.add(3, Direction.DOWN)
        self.chains.future_chain.add(3, Direction.UP)

        # TestCase 1
        self.chains.remove(a2)
        self.assertNotIn(a2, self.chains.next_chain)

        # TestCase 2
        self.chains.remove(a3)
        self.assertNotIn(a3, self.chains.future_chain)

        # TestCase 3
        self.chains.remove(a1)
        self.assertNotIn(a1, self.chains.current_chain)

        # TestCase 4
        self.chains.remove(a4)
        self.assertEqual(self.chains.direction, Direction.DOWN)
        self.assertNotIn(a4, self.chains.future_chain)

        # TestCase 5
        self.chains.remove(a5)
        self.assertTrue(self.chains.is_empty())
        self.assertEqual(self.chains.direction, Direction.IDLE)

    def testis_empty(self):
        # TestCase 1
        self.assertTrue(self.chains.is_empty())

        # TestCase 2
        self.chains.current_chain.add(1, Direction.IDLE)
        self.chains.next_chain.add(2, Direction.IDLE)

    def test_clear_and_len(self):
        self.chains.direction = Direction.DOWN
        # TestCase of _len_()
        self.chains.current_chain.add(1, Direction.DOWN)
        self.chains.next_chain.add(2, Direction.UP)
        self.assertEqual(len(self.chains), 2)

        # TestCase of clear()
        self.chains.clear()
        self.assertEqual(len(self.chains), 0)

    def test_copy(self):
        a = FloorAction(1, Direction.IDLE)
        self.chains.current_chain.add(1, Direction.IDLE)
        new_chains = self.chains.__copy__()
        self.assertIn(a, new_chains)
        self.assertIsNot(self.chains.current_chain, new_chains.current_chain)

    def test_contains_and_getitem(self):
        a1 = FloorAction(1, Direction.IDLE)
        a2 = FloorAction(2, Direction.IDLE)
        a3 = FloorAction(3, Direction.IDLE)
        self.chains.current_chain.add(1, Direction.IDLE)
        self.chains.next_chain.add(2, Direction.IDLE)
        self.chains.future_chain.add(3, Direction.IDLE)

        # TestCase of _contains_
        self.assertIn(a2, self.chains)

        # TestCase of _getitem_
        # TestCase 1
        self.assertEqual(self.chains[-3], a1)

        # TestCase 2
        self.assertEqual(self.chains[1], a2)

        # TestCase 3
        self.assertEqual(self.chains[2], a3)

        # TestCase 4
        with self.assertRaises(IndexError):
            _ = self.chains[5]


if __name__ == "__main__":
    try:
        unittest.main()
    except KeyboardInterrupt:
        pass
