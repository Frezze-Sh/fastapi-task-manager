from pydantic import BaseModel, EmailStr
import uvicorn
from fastapi.security import OAuth2PasswordRequestForm
from fastapi import FastAPI, HTTPException, Depends, status
from typing import Optional, List
from datetime import datetime
from database import get_connection
import psycopg2
from psycopg2.extras import RealDictCursor
from auth import hash_password, verify_password, create_access_token, get_current_user

app = FastAPI(title="Task Manager API", description="API для управления задачами", swagger_ui_parameters={"operationsSorter": None})

# Pydantic модели
class TaskCreate(BaseModel):
    #Модель для создания задачи (user_id убран - берётся из токена)
    title: str
    description: Optional[str] = None
    priority: Optional[int] = 2
    estimated_minutes: Optional[int] = None
    category_id: Optional[int] = None

class TaskUpdate(BaseModel):
    #Модель для обновления задачи (все поля опциональны)
    title: Optional[str] = None
    description: Optional[str] = None
    done: Optional[bool] = None
    priority: Optional[int] = None
    estimated_minutes: Optional[int] = None
    category_id: Optional[int] = None

class TaskResponse(BaseModel):
    #Модель для ответа (все поля, которые есть в БД)
    id: int
    title: str
    description: Optional[str] = None
    done: bool
    user_id: Optional[int] = None
    category_id: Optional[int] = None
    priority: int
    created_at: datetime
    updated_at: datetime
    estimated_minutes: Optional[int] = None

class CategoryResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None

class UserCreate(BaseModel):
    name: str
    email: str
    is_active: Optional[bool] = True

class UserResponse(BaseModel):
    id: int
    name: str
    email: Optional[str] = None
    is_active: bool
    created_at: datetime

class UserRegister(BaseModel):
    #Модель для регистрации
    name: str
    email: EmailStr
    password: str

class UserLogin(BaseModel):
    #Модель для логина
    email: EmailStr
    password: str

class Token(BaseModel):
    #Модель ответа с токеном
    access_token: str
    token_type: str = "bearer"

class UserDeleteResponse(BaseModel):
    #Модель ответа при успешном удалении пользователя
    message: str
    deleted_user: UserResponse

# Эндпоинты
@app.get("/", tags=["Root"])
def root():
    return {"message": "Task API работает с PostgreSQL!"}

#--------------------------------------------------------------------------------------------
# Аутентификация (публичные эндпоинты)
@app.post("/register", response_model=UserResponse, tags=["Аутентификация"])
def register(user: UserRegister):
    """Регистрация нового пользователя"""
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Проверяем, нет ли уже пользователя с таким email
    cur.execute("SELECT id FROM users WHERE email = %s", (user.email,))
    if cur.fetchone():
        cur.close()
        conn.close()
        raise HTTPException(
            status_code=400,
            detail="Пользователь с таким email уже существует"
        )

    # Хешируем пароль
    hashed_password = hash_password(user.password)

    # Создаём пользователя
    cur.execute("""
        INSERT INTO users (name, email, hashed_password, is_active)
        VALUES (%s, %s, %s, %s)
        RETURNING id, name, email, is_active, created_at
    """, (user.name, user.email, hashed_password, True))

    new_user = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()

    return dict(new_user)

@app.post("/login", response_model=Token, tags=["Аутентификация"])
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    email = form_data.username
    password = form_data.password

    cur.execute("SELECT id, hashed_password FROM users WHERE email = %s", (email,))
    db_user = cur.fetchone()
    cur.close()
    conn.close()

    if not db_user or not verify_password(password, db_user["hashed_password"]):
        raise HTTPException(
            status_code=401,
            detail="Неверный email или пароль",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = db_user["id"]
    print(f"Creating token for user_id: {user_id}, type: {type(user_id)}")  # Для отладки

    access_token = create_access_token(data={"sub": str(user_id)})  # ← ЯВНО преобразуем в строку
    return {"access_token": access_token, "token_type": "bearer"}

#-------------------------------------------------------------------------------------------
# Защищённые эндпоинты для пользователей
@app.get("/users/me/tasks", response_model=List[TaskResponse], tags=["Зарегистрированные пользователи"])
def get_my_tasks(current_user: dict = Depends(get_current_user)):
    """Получить задачи текущего пользователя"""
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("""
        SELECT id, title, description, done, user_id, category_id, 
               priority, created_at, updated_at, estimated_minutes
        FROM tasks 
        WHERE user_id = %s
        ORDER BY created_at DESC
    """, (current_user["id"],))
    tasks = cur.fetchall()
    cur.close()
    conn.close()

    return [dict(t) for t in tasks]

@app.get("/users/me", response_model=UserResponse, tags=["Зарегистрированные пользователи"])
def get_current_user_profile(current_user: dict = Depends(get_current_user)):
    """Получить данные текущего пользователя"""
    return current_user


@app.post("/tasks", response_model=TaskResponse, tags=["Зарегистрированные пользователи"])
def create_task(task: TaskCreate, current_user: dict = Depends(get_current_user)):
    """Создать задачу для текущего пользователя"""
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            INSERT INTO tasks (title, description, priority, estimated_minutes, category_id, user_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id, title, description, done, user_id, category_id,
                      priority, created_at, updated_at, estimated_minutes
        """, (
            task.title, task.description, task.priority,
            task.estimated_minutes, task.category_id, current_user["id"]
        ))
        new_task = cur.fetchone()
        conn.commit()
    except psycopg2.errors.ForeignKeyViolation:
        conn.rollback()
        cur.close()
        conn.close()
        raise HTTPException(
            status_code=400,
            detail="Ошибка: указанная категория не найдена в базе данных."
        )
    finally:
        cur.close()
        conn.close()

    return dict(new_task)


@app.put("/tasks/{task_id}", response_model=TaskResponse, tags=["Зарегистрированные пользователи"])
def update_task(task_id: int, task: TaskUpdate, current_user: dict = Depends(get_current_user)):
    """Обновить определённую задачу у текущего пользователя"""
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("SELECT * FROM tasks WHERE id = %s", (task_id,))
    existing = cur.fetchone()
    if not existing:
        cur.close()
        conn.close()
        raise HTTPException(status_code=404, detail="Задача не найдена")

    # Проверяем, что задача принадлежит текущему пользователю
    if existing["user_id"] != current_user["id"]:
        cur.close()
        conn.close()
        raise HTTPException(status_code=403, detail="Вы не можете редактировать чужие задачи")

    cur.execute("""
        UPDATE tasks 
        SET title = COALESCE(%s, title),
            description = COALESCE(%s, description),
            done = COALESCE(%s, done),
            priority = COALESCE(%s, priority),
            estimated_minutes = COALESCE(%s, estimated_minutes),
            category_id = COALESCE(%s, category_id),
            updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
        RETURNING id, title, description, done, user_id, category_id,
                  priority, created_at, updated_at, estimated_minutes
    """, (
        task.title, task.description, task.done, task.priority,
        task.estimated_minutes, task.category_id, task_id
    ))

    updated = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()

    return dict(updated)


@app.patch("/tasks/{task_id}/done", response_model=TaskResponse, tags=["Зарегистрированные пользователи"])
def mark_done(task_id: int, current_user: dict = Depends(get_current_user)):
    """Отметить определённую задачу выполненной у текущего пользователя"""
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Проверяем, что задача принадлежит текущему пользователю
    cur.execute("SELECT user_id FROM tasks WHERE id = %s", (task_id,))
    task = cur.fetchone()

    if not task:
        cur.close()
        conn.close()
        raise HTTPException(status_code=404, detail="Задача не найдена")

    if task["user_id"] != current_user["id"]:
        cur.close()
        conn.close()
        raise HTTPException(status_code=403, detail="Вы не можете изменять чужие задачи")

    cur.execute("""
        UPDATE tasks
        SET done = TRUE, updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
        RETURNING id, title, description, done, user_id, category_id,
                  priority, created_at, updated_at, estimated_minutes
    """, (task_id,))
    updated = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()

    return dict(updated)


@app.delete("/tasks/{task_id}", tags=["Зарегистрированные пользователи"])
def delete_task(task_id: int, current_user: dict = Depends(get_current_user)):
    """Удалить определённую задачу у текущего пользователя"""
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Проверяем, что задача принадлежит текущему пользователю
    cur.execute("SELECT user_id FROM tasks WHERE id = %s", (task_id,))
    task = cur.fetchone()

    if not task:
        cur.close()
        conn.close()
        raise HTTPException(status_code=404, detail="Задача не найдена")

    if task["user_id"] != current_user["id"]:
        cur.close()
        conn.close()
        raise HTTPException(status_code=403, detail="Вы не можете удалять чужие задачи")

    cur.execute("DELETE FROM tasks WHERE id = %s RETURNING id", (task_id,))
    deleted = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()

    return {"message": f"Задача {task_id} удалена"}


@app.delete("/users/me", response_model=UserDeleteResponse, tags=["Зарегистрированные пользователи"])
def delete_current_user(current_user: dict = Depends(get_current_user)):
    """
    Удалить текущего пользователя.

    После удаления аккаунта:
    1. Нажмите зелёный замочек в правом верхнем углу Swagger UI
    2. Нажмите кнопку "Logout"
    3. Токен будет удалён из браузера
    """
    #Удалить текущего пользователя
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        cur.execute("""
            DELETE FROM users 
            WHERE id = %s 
            RETURNING id, name, email, is_active, created_at
        """, (current_user["id"],))

        deleted_user = cur.fetchone()

        if not deleted_user:
            raise HTTPException(status_code=404, detail="Пользователь не найден")

        conn.commit()

        return {
            "message": f"Пользователь '{deleted_user['name']}' (ID: {deleted_user['id']}) и все его задачи успешно удалены",
            "deleted_user": dict(deleted_user)
        }

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Ошибка сервера при удалении пользователя: {str(e)}")
    finally:
        cur.close()
        conn.close()

#--------------------------------------------------------------------------------------------
# Публичные эндпоинты для пользователей
@app.get("/categories", response_model=List[CategoryResponse], tags=["Публичные пользователи"])
def get_all_categories():
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT id, name, description, color, icon FROM categories ORDER BY name")
    categories = cur.fetchall()
    cur.close()
    conn.close()

    return [dict(c) for c in categories]


@app.get("/tasks", response_model=List[TaskResponse], tags=["Публичные пользователи"])
def get_all_tasks(category_id: Optional[int] = None):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    if category_id is not None:
        cur.execute("SELECT id FROM categories WHERE id = %s", (category_id,))
        if not cur.fetchone():
            cur.close()
            conn.close()
            raise HTTPException(status_code=404, detail="Категория не найдена")

        cur.execute("""
            SELECT id, title, description, done, user_id, category_id, 
                   priority, created_at, updated_at, estimated_minutes
            FROM tasks 
            WHERE category_id = %s
            ORDER BY created_at DESC
        """, (category_id,))
    else:
        cur.execute("""
            SELECT id, title, description, done, user_id, category_id, 
                   priority, created_at, updated_at, estimated_minutes
            FROM tasks
            ORDER BY created_at DESC
        """)

    tasks = cur.fetchall()
    cur.close()
    conn.close()

    return [dict(t) for t in tasks]


@app.get("/tasks/{task_id}", response_model=TaskResponse, tags=["Публичные пользователи"])
def get_task(task_id: int):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT id, title, description, done, user_id, category_id,
               priority, created_at, updated_at, estimated_minutes
        FROM tasks WHERE id = %s
    """, (task_id,))
    task = cur.fetchone()
    cur.close()
    conn.close()

    if not task:
        raise HTTPException(status_code=404, detail="Задача не найдена")

    return dict(task)


@app.get("/users", response_model=List[UserResponse], tags=["Публичные пользователи"])
def get_all_users():
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT id, name, email, is_active, created_at FROM users ORDER BY id")
    users = cur.fetchall()
    cur.close()
    conn.close()

    return [dict(u) for u in users]


@app.get("/users/{user_id}/tasks", response_model=List[TaskResponse], tags=["Публичные пользователи"])
def get_tasks_by_user(user_id: int):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("SELECT id FROM users WHERE id = %s", (user_id,))
    if not cur.fetchone():
        cur.close()
        conn.close()
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    cur.execute("""
        SELECT id, title, description, done, user_id, category_id, 
               priority, created_at, updated_at, estimated_minutes
        FROM tasks 
        WHERE user_id = %s
        ORDER BY created_at DESC
    """, (user_id,))
    tasks = cur.fetchall()
    cur.close()
    conn.close()

    return [dict(t) for t in tasks]


@app.post("/users", response_model=UserResponse, tags=["Публичные пользователи"])
def create_user(user: UserCreate):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        INSERT INTO users (name, email, is_active)
        VALUES (%s, %s, %s)
        RETURNING id, name, email, is_active, created_at
    """, (user.name, user.email, user.is_active))
    new_user = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()

    return dict(new_user)


@app.delete("/users/{user_id}", response_model=UserDeleteResponse, tags=["Публичные пользователи"])
def delete_user(user_id: int):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        cur.execute("""
            DELETE FROM users 
            WHERE id = %s 
            RETURNING id, name, email, is_active, created_at
        """, (user_id,))

        deleted_user = cur.fetchone()

        if not deleted_user:
            raise HTTPException(status_code=404, detail="Пользователь не найден")

        conn.commit()

        return {
            "message": f"Пользователь '{deleted_user['name']}' (ID: {deleted_user['id']}) и все его задачи успешно удалены",
            "deleted_user": dict(deleted_user)
        }

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Ошибка сервера при удалении пользователя: {str(e)}")
    finally:
        cur.close()
        conn.close()

#--------------------------------------------------------------------------------------------
if __name__ == "__main__":
    uvicorn.run("main:app", reload=True)

