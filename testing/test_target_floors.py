import unittest

from common import FloorAction, Direction, TargetFloors


class TestTargetFloors(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.up = Direction.UP
        self.down = Direction.DOWN
        self.idle = Direction.IDLE

    def test_add(self):
        tf = TargetFloors(self.up)
        # TestCase 1
        with self.assertRaises(AssertionError):
            tf.add(2, self.down)

        # TestCase 2
        self.assertFalse(tf.nonemptyEvent.is_set())

        # TestCase 3
        tf.add(3, self.up)
        tf.add(1, self.up)
        tf.add(5, self.up)
        self.assertEqual(list(tf), [FloorAction(1, self.up), FloorAction(3, self.up), FloorAction(5, self.up)])
        self.assertTrue(tf.nonemptyEvent.is_set())

    def test_remove(self):
        tf = TargetFloors(self.up)
        tf.add(3, self.up)
        tf.add(1, self.up)
        tf.remove(FloorAction(3, self.up))
        # TestCase 1
        self.assertNotIn(FloorAction(3, self.up), tf)

        # TestCase 2
        tf.remove(FloorAction(1, self.up))
        self.assertFalse(tf.nonemptyEvent.is_set())

    def test_pop(self):
        tf = TargetFloors(self.down)
        tf.add(1, self.down)
        tf.add(2, self.down)
        action = tf.pop()
        # TestCase 1
        self.assertEqual(action, FloorAction(1, self.down))

        # TestCase 2
        tf.pop()
        self.assertFalse(tf.nonemptyEvent.is_set())

    def test_is_empty(self):
        tf = TargetFloors(self.down)
        # TestCase 1
        tf.add(1, self.down)
        self.assertFalse(tf.is_empty())

        # TestCase 2
        tf.pop()
        self.assertTrue(tf.is_empty())

    def test_copy(self):
        tf = TargetFloors(self.down)
        tf_copy1 = tf.copy()
        tf.add(4, self.down)
        tf_copy2 = tf.copy()
        self.assertEqual(list(tf), list(tf_copy2))
        self.assertNotEqual(tf.nonemptyEvent, tf_copy2.nonemptyEvent)

        # TestCase 1
        self.assertTrue(tf_copy2.nonemptyEvent.is_set())

        # TestCase 2
        self.assertFalse(tf_copy1.nonemptyEvent.is_set())

    def test_direction(self):
        tf = TargetFloors(self.down)

        # TestCase 1
        tf.add(1, self.down)
        tf.add(2, self.down)

        sorted_actions = sorted(tf, key=tf.key)
        expected_order = [FloorAction(2, Direction.DOWN), FloorAction(1, Direction.DOWN)]
        self.assertEqual(tf.direction, self.down)
        self.assertEqual(sorted_actions, expected_order)

        # TestCase 2
        tf.direction = self.down
        self.assertEqual(tf.direction, self.down)

        # TestCase 3
        with self.assertRaises(AssertionError):
            tf.direction = self.up

        # TestCase 4
        tf.pop()
        tf.pop()
        tf.direction = self.up

        tf.add(2, self.up)
        tf.add(1, self.up)
        sorted_actions_up = sorted(tf, key=tf.key)
        expected_order_up = [FloorAction(1, Direction.UP), FloorAction(2, Direction.UP)]
        self.assertEqual(tf.direction, self.up)
        self.assertEqual(sorted_actions_up, expected_order_up)

        # TestCase 5
        tf.pop()
        tf.pop()
        tf.direction = self.idle
        self.assertEqual(tf.direction, self.idle)
        self.assertIsNone(tf.key)


if __name__ == "__main__":
    try:
        unittest.main()
    except KeyboardInterrupt:
        pass
