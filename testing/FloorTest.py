import unittest
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from system.utils.common import Floor, Direction

# Floor 类代码略（请用你自己的）

class TestFloor(unittest.TestCase):

    def test_construction(self):
        # TestCase 1
        self.assertEqual(Floor(3), 3)
        
        # TestCase 2
        self.assertEqual(Floor("-2"), -1)

    def test_str_and_repr(self):
        # TestCase of _str_
        # TestCase 1
        self.assertEqual(str(Floor(3)), "3")

        # TestCase 2
        self.assertEqual(str(Floor(-1)), "-1")  # 0 显示为 -1

        # TestCase of _repr_
        self.assertEqual(repr(Floor(3)), "Floor(3)")

    def test_add_sub(self):
        # TestCase of _add_
        self.assertEqual(Floor(2) + 3, Floor(5))

        # TestCase of _sub_
        self.assertEqual(Floor(2) - 3, Floor(-2))
        

    def test_direction_to(self):
        # TestCase 1
        self.assertEqual(Floor(2).direction_to(Floor(3)), Direction.UP)

        # TestCase 2
        self.assertEqual(Floor(5).direction_to(Floor(2)), Direction.DOWN)

        # TestCase 3
        self.assertEqual(Floor(3).direction_to(Floor(3)), Direction.IDLE)

    def test_between(self):
        # TestCase 1
        self.assertTrue(Floor(3).between(Floor(2), Floor(5)))

        # TestCase 2
        self.assertFalse(Floor(1).between(Floor(2), Floor(5)))

    def test_is_of(self):
        # TestCase 1
        self.assertTrue(Floor(3).is_of(Direction.UP, Floor(5)))

        # TestCase 2
        self.assertFalse(Floor(3).is_of(Direction.DOWN, Floor(5)))

        # TestCase 3
        self.assertFalse(Floor(3).is_of(Direction.IDLE, Floor(5)))

if __name__ == "__main__":
    unittest.main()
