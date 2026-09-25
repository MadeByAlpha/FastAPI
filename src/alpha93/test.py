from fastapi import FastAPI

app = FastAPI(
    title=""
)

@app.get("/test")
def test():
    ...
