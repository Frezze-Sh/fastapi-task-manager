from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException, status, Depends
from fastapi.security import OAuth2PasswordBearer
from database import get_connection
from psycopg2.extras import RealDictCursor

# Секретный ключ для подписи JWT
SECRET_KEY = "your-super-secret-key-change-this-in-production-12345"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30  # Токен живёт 30 минут

# Настройка хеширования паролей
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Схема для получения токена из заголовка Authorization
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def hash_password(password: str) -> str:
    #Хеширует пароль
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    #Проверяет, совпадает ли пароль с хешем
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def get_current_user(token: str = Depends(oauth2_scheme)):
    #Зависимость FastAPI: извлекает пользователя из токена.
    #Используется в эндпоинтах как: current_user: dict = Depends(get_current_user)
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Неверные учётные данные",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        # Декодируем токен без проверки срока действия (для отладки!)
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM], options={"verify_exp": False})
        print(f"PAYLOAD из токена: {payload}")  # ← Добавлено для отладки

        user_id_str: str = payload.get("sub")
        if user_id_str is None:
            print("sub не найден в токене")
            raise credentials_exception

        user_id = int(user_id_str)
        print(f"user_id из токена: {user_id}")

    except JWTError as e:
        print(f"WTError: {e}")
        raise credentials_exception
    except ValueError as e:
        print(f"ValueError: {e}")
        raise credentials_exception

    # Проверяем, существует ли пользователь в БД
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT id, name, email, is_active, created_at FROM users WHERE id = %s", (user_id,))
    user = cur.fetchone()
    cur.close()
    conn.close()

    if user is None:
        raise credentials_exception

    return dict(user)