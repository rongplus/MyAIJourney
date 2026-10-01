from fastapi import FastAPI
from user import user
from game import game
from interface import interface

app = FastAPI()

app.include_router(user.router)
app.include_router(game.router)
app.include_router(interface.router)
