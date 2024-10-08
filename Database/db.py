from fastapi import FastAPI
from sqlmodel import SQLModel
from Database.setting import engine


async def create_tables(app:FastAPI):
    print(F"create_tables...{app}")
    # start_ngrok()
    SQLModel.metadata.create_all(bind = engine)
    yield