from fastapi import Request, HTTPException, Depends
from core.config import config_manager

async def verify_token(request: Request):
    """
    Универсальная проверка токена.
    Поддерживает:
    1. Authorization: Bearer <token> (Стандарт)
    2. X-Token: <token> (Устаревший, для совместимости)
    3. ?token=<token> (Для простых GET запросов)
    """
    token = None
    
    # 1. Проверяем стандартный заголовок Authorization
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
    
    # 2. Проверяем устаревший заголовок X-Token
    if not token:
        token = request.headers.get("X-Token")
        
    # 3. Проверяем параметры запроса
    if not token:
        token = request.query_params.get("token") or request.query_params.get("gui_token")

    if not token:
        raise HTTPException(status_code=401, detail="Token missing")

    cfg = config_manager.get()
    
    # Список всех допустимых токенов
    valid_tokens = []
    if config_manager.gui_token:
        valid_tokens.append(config_manager.gui_token)
    
    if hasattr(cfg, 'trusted_tokens') and cfg.trusted_tokens:
        valid_tokens.extend(cfg.trusted_tokens)

    if token not in valid_tokens:
        raise HTTPException(status_code=401, detail="Invalid token")
        
    return token
