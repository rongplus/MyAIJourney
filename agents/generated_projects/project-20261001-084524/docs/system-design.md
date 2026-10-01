# 系统设计

系统设计：

1. 模块职责：
   - 用户模块：负责用户注册、登录、创建和加入对局。
   - 游戏模块：负责棋盘显示、棋子移动、胜负判断。
   - 界面模块：负责用户界面的展示和交互。

2. 数据流：
   - 用户模块：用户注册信息、登录信息、对局信息。
   - 游戏模块：棋盘状态、棋子位置、移动记录。
   - 界面模块：用户操作、游戏状态显示。

3. 关键接口：
   - 用户模块：注册接口、登录接口、创建对局接口、加入对局接口。
   - 游戏模块：初始化棋盘接口、移动棋子接口、判断胜负接口。
   - 界面模块：显示棋盘接口、接收用户操作接口。

4. 错误处理：
   - 用户模块：处理注册失败、登录失败、对局创建失败、对局加入失败等错误。
   - 游戏模块：处理非法移动、棋子不存在等错误。
   - 界面模块：处理用户操作错误、游戏状态显示错误。

5. 测试策略：
   - 单元测试：对每个模块的每个函数进行测试。
   - 集成测试：对模块之间的交互进行测试。
   - 系统测试：对整个系统进行测试。

6. 目录结构：
   - app/
     - main.py
     - user/
       - __init__.py
       - user.py
     - game/
       - __init__.py
       - game.py
     - interface/
       - __init__.py
       - interface.py

main.py:
```python
from fastapi import FastAPI
from user import user
from game import game
from interface import interface

app = FastAPI()

app.include_router(user.router)
app.include_router(game.router)
app.include_router(interface.router)
```

user.py:
```python
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
```

game.py:
```python
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

class Game(BaseModel):
    board: list
    turn: str

@router.post("/init_board/")
async def init_board():
    # 初始化棋盘逻辑
    pass

@router.post("/move_piece/")
async def move_piece(game: Game, from_pos: str, to_pos: str):
    # 移动棋子逻辑
    pass

@router.post("/check_winner/")
async def check_winner(game: Game):
    # 判断胜负逻辑
    pass
```

interface.py:
```python
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

class Move(BaseModel):
    from_pos: str
    to_pos: str

@router.post("/display_board/")
async def display_board(game: Game):
    # 显示棋盘逻辑
    pass

@router.post("/receive_move/")
async def receive_move(move: Move):
    # 接收用户操作逻辑
    pass
```
