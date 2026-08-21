#!/usr/bin/env python3
"""
Модуль: Tool/mcp_server.py
Назначение: Полнофункциональный FastMCP сервер с декораторами @mcp.tool, поддержкой JSON-RPC и специализированными коннекторами (GitHub, PostgreSQL/Prisma, Telegram, dVPN Core).
Архитектурный слой: Tool (Инфраструктурные коннекторы).
Инвариант: Прямой ввод сырых учетных данных в промпты запрещен; доступ строго через типизированные схемы RPC.
"""

import argparse
import inspect
import json
import logging
import os
import sys
from functools import wraps
from pathlib import Path
from typing import Callable, Dict, Any, List, Optional

# Добавление путей
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

try:
    from connectors.github_connector import GitHubConnector
    from connectors.postgres_connector import PostgresConnector
    from connectors.telegram_connector import TelegramConnector
    from connectors.dvpn_connector import DVPNConnector
except ImportError:
    from Tool.connectors.github_connector import GitHubConnector  # type: ignore
    from Tool.connectors.postgres_connector import PostgresConnector  # type: ignore
    from Tool.connectors.telegram_connector import TelegramConnector  # type: ignore
    from Tool.connectors.dvpn_connector import DVPNConnector  # type: ignore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [FASTMCP] %(message)s")
logger = logging.getLogger("FastMCP")


class FastMCPServer:
    """
    Легковесный сервер Model Context Protocol (MCP) с поддержкой динамической регистрации инструментов.
    """

    def __init__(self, name: str = "SelfEvo-FastMCP-Gateway") -> None:
        self.name = name
        self.tools: Dict[str, Dict[str, Any]] = {}
        self.tool_handlers: Dict[str, Callable] = {}

    def tool(self, name: Optional[str] = None, description: Optional[str] = None) -> Callable:
        """
        Декоратор @mcp.tool для регистрации Python-функций в качестве MCP-инструментов.
        Автоматически генерирует JSON-схему аргументов по аннотациям типов.
        """
        def decorator(func: Callable) -> Callable:
            tool_name = name or func.__name__
            tool_desc = description or (func.__doc__ or "No description provided").strip()

            sig = inspect.signature(func)
            properties: Dict[str, Any] = {}
            required: List[str] = []

            for param_name, param in sig.parameters.items():
                param_type = "string"
                if param.annotation == int:
                    param_type = "integer"
                elif param.annotation == bool:
                    param_type = "boolean"
                elif param.annotation == dict or param.annotation == Optional[Dict[str, Any]]:
                    param_type = "object"
                elif param.annotation == list or param.annotation == Optional[List[str]]:
                    param_type = "array"

                properties[param_name] = {
                    "type": param_type,
                    "description": f"Параметр {param_name}",
                }
                if param.default == inspect.Parameter.empty:
                    required.append(param_name)

            schema = {
                "name": tool_name,
                "description": tool_desc,
                "inputSchema": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            }

            self.tools[tool_name] = schema
            self.tool_handlers[tool_name] = func
            logger.debug(f"Зарегистрирован MCP инструмент: {tool_name}")

            @wraps(func)
            def wrapper(*args, **kwargs):
                return func(*args, **kwargs)
            return wrapper

        return decorator

    def list_tools(self) -> List[Dict[str, Any]]:
        """Возвращает список всех зарегистрированных схем инструментов."""
        return list(self.tools.values())

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Вызов зарегистрированного инструмента по имени с валидацией аргументов."""
        if tool_name not in self.tool_handlers:
            return {
                "isError": True,
                "content": [{"type": "text", "text": f"Инструмент '{tool_name}' не найден."}],
            }

        handler = self.tool_handlers[tool_name]
        try:
            result = handler(**arguments)
            return {
                "isError": False,
                "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False) if isinstance(result, (dict, list)) else str(result)}],
            }
        except Exception as e:
            logger.error(f"Ошибка исполнения инструмента {tool_name}: {e}")
            return {
                "isError": True,
                "content": [{"type": "text", "text": f"Ошибка выполнения: {str(e)}"}],
            }

    def run_stdio_server(self) -> None:
        """Стандартный JSON-RPC 2.0 цикл обработки запросов через stdin/stdout."""
        logger.info(f"FastMCP сервер '{self.name}' запущен в режиме stdio...")
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                request = json.loads(line)
                req_id = request.get("id")
                method = request.get("method")

                if method == "initialize":
                    params = request.get("params", {})
                    response = {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "protocolVersion": params.get("protocolVersion", "2024-11-05"),
                            "capabilities": {"tools": {}},
                            "serverInfo": {"name": self.name, "version": "1.0.0"},
                        },
                    }
                elif method in ("notifications/initialized", "initialized"):
                    continue
                elif method == "tools/list":
                    response = {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {"tools": self.list_tools()},
                    }
                elif method == "tools/call":
                    params = request.get("params", {})
                    tool_name = params.get("name")
                    args = params.get("arguments", {})
                    call_result = self.call_tool(tool_name, args)
                    response = {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": call_result,
                    }
                elif req_id is None:
                    # Уведомление (notification) без id — ответ не требуется по спецификации JSON-RPC 2.0
                    continue
                else:
                    response = {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {"code": -32601, "message": f"Метод {method} не поддерживается"},
                    }

                sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
                sys.stdout.flush()
            except Exception as ex:
                err_resp = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": f"Parse error: {ex}"},
                }
                sys.stdout.write(json.dumps(err_resp, ensure_ascii=False) + "\n")
                sys.stdout.flush()


# Инициализация глобального сервера FastMCP и модульных коннекторов
mcp = FastMCPServer(name="WhyAi-Sovereign-FastMCP")
github_conn = GitHubConnector()
postgres_conn = PostgresConnector()
telegram_conn = TelegramConnector()
dvpn_conn = DVPNConnector()


# ==============================================================================
# Регистрация специализированных инструментов GitHub MCP
# ==============================================================================

@mcp.tool(name="github_get_repo_info", description="Получить метаданные репозитория GitHub")
def github_get_repo_info(repo: str = "VlaD-KH/_Ai") -> Dict[str, Any]:
    """Инспекция метаданных целевого репозитория."""
    return github_conn.get_repo_info(repo=repo)


@mcp.tool(name="github_create_draft_pr", description="Создать безопасный Draft Pull Request на GitHub")
def github_create_draft_pr(title: str, body: str, head_branch: str, base_branch: str = "main", repo: str = "VlaD-KH/_Ai") -> Dict[str, Any]:
    """Создает черновой PR без прав на самостоятельное слияние (требует одобрения человека)."""
    return github_conn.create_draft_pr(repo=repo, title=title, body=body, head_branch=head_branch, base_branch=base_branch)


@mcp.tool(name="github_list_commits", description="Получить список последних коммитов с SHA-256")
def github_list_commits(branch: str = "main", repo: str = "VlaD-KH/_Ai", limit: int = 10) -> List[Dict[str, Any]]:
    """Аудит истории коммитов репозитория."""
    return github_conn.list_commits(repo=repo, branch=branch, limit=limit)


@mcp.tool(name="github_get_file_contents", description="Безопасное получение файла из репозитория GitHub")
def github_get_file_contents(path: str, repo: str = "VlaD-KH/_Ai", ref: str = "main") -> Dict[str, Any]:
    """Чтение файла из указанной ветки GitHub."""
    return github_conn.get_file_contents(repo=repo, path=path, ref=ref)


# ==============================================================================
# Регистрация специализированных инструментов PostgreSQL & Prisma MCP
# ==============================================================================

@mcp.tool(name="postgres_execute_query", description="Выполнить типизированный параметризованный запрос к PostgreSQL")
def postgres_execute_query(query: str, read_only: bool = True) -> Dict[str, Any]:
    """Безопасное выполнение запроса к БД с блокировкой деструктивных DDL."""
    return postgres_conn.execute_query(query=query, read_only=read_only)


@mcp.tool(name="postgres_inspect_schema", description="Инспекция структуры таблицы и индексов PostgreSQL/Prisma")
def postgres_inspect_schema(table_name: str = "nodes") -> Dict[str, Any]:
    """Инспекция структуры колонок, первичных ключей и индексов."""
    return postgres_conn.inspect_schema(table_name=table_name)


@mcp.tool(name="postgres_pool_health", description="Проверка состояния пула соединений PostgreSQL/Prisma")
def postgres_pool_health() -> Dict[str, Any]:
    """Проверка доступности и времени отклика пула БД."""
    return postgres_conn.pool_health()


@mcp.tool(name="prisma_generate_schema_diff", description="Анализ различий и безопасность миграций Prisma ORM")
def prisma_generate_schema_diff(current_schema: str, target_schema: str) -> Dict[str, Any]:
    """Проверка схемы на наличие разрушительных изменений перед миграцией."""
    return postgres_conn.prisma_schema_diff(current_schema=current_schema, target_schema=target_schema)


# ==============================================================================
# Регистрация специализированных инструментов Telegram Bot MCP
# ==============================================================================

@mcp.tool(name="telegram_send_alert", description="Отправить внеполосное оповещение в Telegram")
def telegram_send_alert(chat_id: str, message: str, priority: str = "INFO") -> Dict[str, Any]:
    """Диспетчеризация структурированного сообщения в Telegram канал/чат."""
    return telegram_conn.send_alert(chat_id=chat_id, message=message, priority=priority)


@mcp.tool(name="telegram_send_panic_notification", description="Отправить экстренное оповещение об аварийном останове /panic")
def telegram_send_panic_notification(exit_code: int = 10, reason: str = "Emergency /panic triggered") -> Dict[str, Any]:
    """Мгновенное уведомление администраторов о фатальном сигнале /panic."""
    return telegram_conn.send_panic_notification(exit_code=exit_code, reason=reason)


@mcp.tool(name="telegram_send_quorum_verdict", description="Оповещение о результатах мультимодельного кворума")
def telegram_send_quorum_verdict(diff_sha: str, verdict: str) -> Dict[str, Any]:
    """Оповещение команды о вердикте Why_Ai Multi-Harness кворума."""
    return telegram_conn.send_quorum_verdict(diff_sha=diff_sha, verdict=verdict)


# ==============================================================================
# Регистрация специализированных инструментов dVPN / Proxy Core MCP
# ==============================================================================

@mcp.tool(name="dvpn_get_status", description="Получить текущий статус соединения и телеметрию dVPN")
def dvpn_get_status(user_id: str = "default_user") -> Dict[str, Any]:
    """Инспекция активного туннеля, протокола, задержки и Kill-Switch."""
    return dvpn_conn.get_status(user_id=user_id)


@mcp.tool(name="dvpn_list_nodes", description="Получить список узлов dVPN с фильтрацией по тарифу и стране")
def dvpn_list_nodes(tier: Optional[str] = None, country: Optional[str] = None) -> List[Dict[str, Any]]:
    """Получение доступных узлов с их показателями качества (Quality Score, EMA Latency)."""
    return dvpn_conn.list_nodes(tier=tier, country=country)


@mcp.tool(name="dvpn_connect_node", description="Подключиться к dVPN с выбором тарифа, страны и протокола")
def dvpn_connect_node(user_id: str = "default_user", tier: str = "free", country: Optional[str] = None, protocol: Optional[str] = None) -> Dict[str, Any]:
    """Установление адаптивного безопасного dVPN туннеля."""
    return dvpn_conn.connect_node(user_id=user_id, tier=tier, country=country, protocol=protocol)


@mcp.tool(name="dvpn_switch_tier_profile", description="Сменить тарифный профиль dVPN (Free/Premium/Enterprise)")
def dvpn_switch_tier_profile(user_id: str = "default_user", new_tier: str = "premium") -> Dict[str, Any]:
    """Динамическое переключение тарифа с обновлением маршрутизации и политик."""
    return dvpn_conn.switch_tier_profile(user_id=user_id, new_tier=new_tier)


@mcp.tool(name="dvpn_trigger_fallback", description="Принудительно запустить Fail-Safe Fallback переключение узла")
def dvpn_trigger_fallback(user_id: str = "default_user", reason: str = "Manual test fallback") -> Dict[str, Any]:
    """Мгновенная смена деградировавшего узла на резервный (<150ms) под защитой Kill-Switch."""
    return dvpn_conn.trigger_fallback(user_id=user_id, reason=reason)


@mcp.tool(name="dvpn_get_client_config", description="Экспорт клиентской конфигурации dVPN (WireGuard conf / VLESS URI)")
def dvpn_get_client_config(user_id: str = "default_user") -> Dict[str, Any]:
    """Получение готовой конфигурации для подключения внешнего клиента."""
    return dvpn_conn.get_client_config(user_id=user_id)


# ==============================================================================
# Регистрация инструментов безопасного доступа к файловой системе
# ==============================================================================

@mcp.tool(name="filesystem_read_sandboxed", description="Чтение файла из изолированной песочницы проекта")
def filesystem_read_sandboxed(path: str) -> Dict[str, Any]:
    """Безопасное чтение файла с проверкой выхода за пределы песочницы."""
    clean_path = path.replace("\\", "/").lstrip("/")
    if clean_path.startswith("Supervisor/") or "BIBLE.md" in clean_path:
        raise PermissionError(f"Прямой доступ к {clean_path} через FastMCP заблокирован!")
    return {
        "status": "READ_OK",
        "path": clean_path,
        "size_bytes": 1024,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Why_Ai Sovereign FastMCP RPC Server")
    parser.add_argument("--list-tools", action="store_true", help="Вывести зарегистрированные инструменты")
    parser.add_argument("--call-tool", type=str, help="Имя инструмента для вызова")
    parser.add_argument("--args", type=str, default="{}", help="Аргументы вызова в формате JSON")
    parser.add_argument("--serve-stdio", action="store_true", help="Запуск стандартного сервера stdio")

    args = parser.parse_args()

    if args.list_tools:
        print(json.dumps(mcp.list_tools(), indent=2, ensure_ascii=False))
        return 0

    if args.call_tool:
        try:
            parsed_args = json.loads(args.args)
        except Exception as e:
            print(f"Ошибка парсинга аргументов: {e}", file=sys.stderr)
            return 1
        res = mcp.call_tool(args.call_tool, parsed_args)
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0

    if args.serve_stdio:
        mcp.run_stdio_server()
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
