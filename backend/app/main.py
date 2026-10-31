from fastapi import FastAPI

app = FastAPI(title="Exercise Form Guide")


@app.get("/")
def root():
    return {"message": "Hello, world!"}


@app.get("/health")
def health():
    return {"status": "ok"}
