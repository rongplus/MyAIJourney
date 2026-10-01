from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

class Move(BaseModel):
    from_pos: str
    to_pos: str

@router.post("/display_board/")
async def display_board(game: Game):
    # 显示棋盘逻辑
    return {"board": game.board, "turn": game.turn}

@router.post("/receive_move/")
async def receive_move(move: Move):
    # 接收用户操作逻辑
    return {"message": "Move received successfully"}
