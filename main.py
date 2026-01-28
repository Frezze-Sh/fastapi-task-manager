from fastapi import FastAPI, HTTPException
import uvicorn
from pydantic import BaseModel

app = FastAPI()

books = [
    {
     "id":1,
     "title":"Асинхронность в Python",
     "author":"Метью"
    },
    {
     "id":2,
     "title":"Бекэнд разработка в Python",
     "author":"Артём"
    }
]

class New_Book(BaseModel):
    title: str
    author: str

@app.get("/books", tags=["Книги"], summary="Получить все книги")
def read_books():
    return books

@app.get("/books/{book_id}", tags=["Книги"], summary="Получить конкретные книги")
def get_book(book_id: int):
    for book in books:
        if book["id"] == book_id:
            return book
    raise HTTPException(status_code=404, detail = "Книга не найдена")

@app.post("/books")
def create_book(new_book:New_Book):
    books.append({
        "id":len(books)+1,
        "title":new_book.title,
        "author":new_book.author
    })
    return {"success":True}

if __name__ == "__main__":
    uvicorn.run("main:app", reload=True)




blacklisted = ["удача"] #input("Навыки, которые находятся в чёрном списке: ")
preferred = ["атака", "защита"] #input("Навыки которые особенно важны: ")
options = (("атака",20),("защита",20),("скорость",10))

def skills(options,preferred,blacklisted):
    preferred_q = []
    neutral = []
    count_black = 0
    count_pref = 0

    for i in range(0,3):
        if options[i][0] in blacklisted:
            count_black+=1
            if count_black == 3:
                return 20
            continue
        elif options[i][0] in preferred:
            count_pref+=1
            preferred_q.append(options[i])
        else:
            neutral.append(options[i])

    if count_pref == 0:
        return max(neutral, key = lambda x: x[1])

    else:
        return max(preferred_q, key = lambda x: x[1])

print(skills(options,preferred,blacklisted))