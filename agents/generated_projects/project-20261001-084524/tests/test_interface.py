import unittest
from app.interface import display_board, receive_move

class TestInterface(unittest.TestCase):
    async def test_display_board(self):
        # 测试显示棋盘逻辑
        game = {"board": [[None]*8 for _ in range(8)], "turn": "white"}
        result = await display_board(game)
        self.assertEqual(len(result["board"]), 8)
        self.assertEqual(len(result["board"][0]), 8)
        self.assertEqual(result["turn"], "white")

    async def test_receive_move(self):
        # 测试接收用户操作逻辑
        move = {"from_pos": "a2", "to_pos": "a4"}
        result = await receive_move(move)
        self.assertEqual(result["message"], "Move received successfully")
