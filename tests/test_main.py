import pytest
import time
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_root():
    """Тест 1: Проверка корневого эндпоинта (Health Check)"""
    response = client.get("/")

    # Проверяем, что сервер ответил 200
    assert response.status_code == 200

    # Проверяем, что вернулся правильный Json
    assert response.json() == {"message": "Task API работает с PostgreSQL!"}


def test_get_categories():
    """Тест 2: Получение категорий (публичный эндпоинт)"""
    response = client.get("/categories")

    assert response.status_code == 200

    # Проверяем, что вернулся список
    data = response.json()
    assert isinstance(data, list)


def test_create_task_unauthorized():
    """Тест 3: Попытка создать задачу БЕЗ токена (должна быть ошибка 401)"""
    # Данные для задачи
    task_data = {
        "title": "Тестовая задача",
        "description": "Создана автотестом",
        "priority": 1,
        "category_id": 1
    }

    # Делаем POST запрос. Токен не передаем.
    response = client.post("/tasks", json=task_data)

    # Ожидаем ошибку 401
    assert response.status_code == 401


def test_register_and_login():
    """Тест полного цикла: регистрация → логин → получение токена"""
    # Генерируем уникальный email с временной меткой
    unique_email = f"pytest_user_{int(time.time())}@test.com"

    # 1. Регистрируем пользователя
    register_data = {
        "name": "Тестовый Юзер",
        "email": unique_email,
        "password": "TestPass123!"
    }
    register_response = client.post("/register", json=register_data)
    assert register_response.status_code == 200

    # 2. Логинимся (получаем токен)
    login_data = {
        "username": unique_email,  # OAuth2 требует username!
        "password": "TestPass123!"
    }
    login_response = client.post("/login", data=login_data)  # data, не json!
    assert login_response.status_code == 200

    # 3. Проверяем, что токен вернулся
    token_data = login_response.json()
    assert "access_token" in token_data
    assert token_data["token_type"] == "bearer"


def test_create_task_with_token():
    """Тест создания задачи С токеном (должно сработать)"""
    # 1. Сначала регистрируемся и логинимся
    register_data = {
        "name": "Task Creator",
        "email": "task_creator@test.com",
        "password": "Pass123!"
    }
    client.post("/register", json=register_data)

    login_data = {
        "username": "task_creator@test.com",
        "password": "Pass123!"
    }
    login_response = client.post("/login", data=login_data)
    token = login_response.json()["access_token"]

    # 2. Создаём задачу с токеном в заголовке
    headers = {"Authorization": f"Bearer {token}"}
    task_data = {
        "title": "Задача с авторизацией",
        "description": "Создана через тест",
        "priority": 1,
        "category_id": 1
    }
    response = client.post("/tasks", json=task_data, headers=headers)

    # 3. Проверяем, что задача создана
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Задача с авторизацией"
    assert "user_id" in data  # user_id должен быть автоматически установлен
    assert "id" in data


def test_get_my_tasks():
    """Тест получения своих задач (/users/me/tasks)"""
    # 1. Регистрируемся и получаем токен
    register_data = {
        "name": "My Tasks User",
        "email": "mytasks@test.com",
        "password": "Pass123!"
    }
    client.post("/register", json=register_data)

    login_data = {
        "username": "mytasks@test.com",
        "password": "Pass123!"
    }
    login_response = client.post("/login", data=login_data)
    token = login_response.json()["access_token"]

    # 2. Создаём пару задач
    headers = {"Authorization": f"Bearer {token}"}
    client.post("/tasks", json={"title": "Задача 1", "category_id": 1}, headers=headers)
    client.post("/tasks", json={"title": "Задача 2", "category_id": 1}, headers=headers)

    # 3. Получаем свои задачи
    response = client.get("/users/me/tasks", headers=headers)
    assert response.status_code == 200

    tasks = response.json()
    assert isinstance(tasks, list)
    assert len(tasks) >= 2  # Должно быть минимум 2 задачи

    # Проверяем, что все задачи принадлежат текущему пользователю
    # (получаем ID текущего пользователя)
    user_response = client.get("/users/me", headers=headers)
    current_user_id = user_response.json()["id"]

    for task in tasks:
        assert task["user_id"] == current_user_id


def test_register_duplicate_email():
    """Тест: регистрация с существующим email (должна быть ошибка 400)"""
    # Сначала регистрируем пользователя
    unique_email = f"dup_test_{int(time.time())}@test.com"
    register_data = {
        "name": "First User",
        "email": unique_email,
        "password": "Pass123!"
    }
    client.post("/register", json=register_data)

    # Пытаемся зарегистрировать того же пользователя
    duplicate_response = client.post("/register", json=register_data)
    assert duplicate_response.status_code == 400
    assert "уже существует" in duplicate_response.json()["detail"]


def test_login_wrong_password():
    """Тест: логин с неверным паролем (должна быть ошибка 401)"""
    unique_email = f"wrong_pass_{int(time.time())}@test.com"
    register_data = {
        "name": "Wrong Pass User",
        "email": unique_email,
        "password": "CorrectPass123!"
    }
    client.post("/register", json=register_data)

    # Пытаемся залогиниться с неверным паролем
    login_data = {
        "username": unique_email,
        "password": "WrongPassword!"
    }
    response = client.post("/login", data=login_data)
    assert response.status_code == 401


def test_get_nonexistent_task():
    """Тест: получение несуществующей задачи (должна быть ошибка 404)"""
    response = client.get("/tasks/99999")
    assert response.status_code == 404
    assert "не найдена" in response.json()["detail"]


def test_update_task():
    """Тест: обновление задачи"""
    # Регистрируемся и создаём задачу
    unique_email = f"update_test_{int(time.time())}@test.com"
    register_data = {"name": "Update User", "email": unique_email, "password": "Pass123!"}
    client.post("/register", json=register_data)

    login_data = {"username": unique_email, "password": "Pass123!"}
    token = client.post("/login", data=login_data).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    task_data = {"title": "Original Title", "category_id": 1}
    task_response = client.post("/tasks", json=task_data, headers=headers)
    task_id = task_response.json()["id"]

    # Обновляем задачу
    update_data = {"title": "Updated Title", "priority": 1}
    update_response = client.put(f"/tasks/{task_id}", json=update_data, headers=headers)
    assert update_response.status_code == 200
    assert update_response.json()["title"] == "Updated Title"


def test_delete_task():
    """Тест: удаление задачи"""
    # Регистрируемся и создаём задачу
    unique_email = f"delete_test_{int(time.time())}@test.com"
    register_data = {"name": "Delete User", "email": unique_email, "password": "Pass123!"}
    client.post("/register", json=register_data)

    login_data = {"username": unique_email, "password": "Pass123!"}
    token = client.post("/login", data=login_data).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    task_data = {"title": "Task to Delete", "category_id": 1}
    task_response = client.post("/tasks", json=task_data, headers=headers)
    task_id = task_response.json()["id"]

    # Удаляем задачу
    delete_response = client.delete(f"/tasks/{task_id}", headers=headers)
    assert delete_response.status_code == 200

    # Проверяем, что задача удалена
    get_response = client.get(f"/tasks/{task_id}")
    assert get_response.status_code == 404


def test_mark_task_done():
    """Тест: отметка задачи выполненной"""
    # Регистрируемся и создаём задачу
    unique_email = f"done_test_{int(time.time())}@test.com"
    register_data = {"name": "Done User", "email": unique_email, "password": "Pass123!"}
    client.post("/register", json=register_data)

    login_data = {"username": unique_email, "password": "Pass123!"}
    token = client.post("/login", data=login_data).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    task_data = {"title": "Task to Mark Done", "category_id": 1}
    task_response = client.post("/tasks", json=task_data, headers=headers)
    task_id = task_response.json()["id"]

    # Отмечаем выполненной
    done_response = client.patch(f"/tasks/{task_id}/done", headers=headers)
    assert done_response.status_code == 200
    assert done_response.json()["done"] == True