import unittest
from app.game import init_board, move_piece, check_winner

class TestGame(unittest.TestCase):
    async def test_init_board(self):
        # 测试初始化棋盘逻辑
        result = await init_board()
        self.assertEqual(len(result["board"]), 8)
        self.assertEqual(len(result["board"][0]), 8)
        self.assertEqual(result["turn"], "white")

    async def test_move_piece(self):
        # 测试移动棋子逻辑
        game = {"board": [[None]*8 for _ in range(8)], "turn": "white"}
        result = await move_piece(game, "a2", "a4")
        self.assertEqual(result["message"], "Piece moved successfully")

    async def test_check_winner(self):
        # 测试判断胜负逻辑
        game = {"board": [[None]*8 for _ in range(8)], "turn": "white"}
        result = await check_winner(game)
        self.assertIsNone(result["winner"])
