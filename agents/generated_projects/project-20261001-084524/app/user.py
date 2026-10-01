from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

class User(BaseModel):
    username: str
    password: str

@router.post("/register/")
async def register(user: User):
    # 注册逻辑
    pass

@router.post("/login/")
async def login(user: User):
    # 登录逻辑
    pass

@router.post("/create_game/")
async def create_game(user: User):
    # 创建对局逻辑
    pass

@router.post("/join_game/")
async def join_game(user: User, game_id: int):
    # 加入对局逻辑
    pass
