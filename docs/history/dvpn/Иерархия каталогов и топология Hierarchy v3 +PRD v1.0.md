###  **Иерархия каталогов и топология Hierarchy v3**

Вы поняли логику **абсолютно верно**. Давайте зафиксируем точное распределение зон, чтобы исключить любые коллизии при классификации диффов:

Plaintext  
Why\_Ai/                           \<-- \[ROOT / HARNESS\] Корень супервизора и ядра ИИ  
├── Supervisor/                   \<-- Zone P/R (Immutable Floor): Чейн политик, BIBLE.md, Commit Gate  
├── Core/                         \<-- Zone E (Mutable Task Runtime): ContextFit, Identity, Engine  
├── Eye/                          \<-- Zone Observability: Telemetry Dock, dashboard.html  
├── .ai-loop/policy/              \<-- ГЛОБАЛЬНАЯ политика ядра (Родительская policy\_layer\_0)  
│   ├── protected\_paths.yaml  
│   └── risk\_classification.yaml  
│  
└── Project\_dVPN/                 \<-- \[TARGET PROJECT\] Внешний целевой модуль (Ранг 1 в \[prod\_evo\])  
    └── .ai-loop/policy/          \<-- ЛОКАЛЬНАЯ политика dVPN (Дочерняя policy\_layer\_1)  
        ├── protected\_paths.yaml  (Запрещает агенту менять, например, серты/конфиги VPS)  
        └── risk\_classification.yaml

**Почему именно так?**  
В режиме \[prod\_evo\] агент переключает фокус на разработку внутри Why\_Ai/Project\_dVPN/. Локальный модуль classify\_diff.py высчитывает итоговый уровень риска любого коммита по каскадному правилу:

$$\\text{Risk}\_{\\text{final}}(\\text{path}) \= \\max(\\text{Risk}\_{\\text{root}}(\\text{path}), \\text{Risk}\_{\\text{dVPN}}(\\text{path}))$$  
Если локальная политика Project\_dVPN попытается ослабить правила корневой политики Why\_Ai, супервизор немедленно заблокирует слияние и инициирует аварийное завершение с Exit Code 10\.

### **Первичный драфт технической спецификации (PRD v1.0)**

#### **Модуль: Adaptive dVPN / Proxy Router (Fallback Core)**

**Контекст разработки:** Выполняется субагентами Planning Scout и Acting Child в контуре \[prod\_evo\] с фиксацией в Why\_Ai/Project\_dVPN/.

### **1\. Product Vision & Value Proposition (Целевое видение)**

* **Название модуля:** dVPN Adaptive Fallback Router ( Why\_Ai-dVPN Core ).  
* **Основная цель:** Обеспечение 100% доступности сетевого соединения в условиях нестабильных каналов, глубокого анализа пакетов (DPI) и таймаутов провайдеров за счет динамической ротации прокси/VPN-профилей с непрерывным мониторингом задержки (RTT) и потери пакетов (Packet Loss).  
* **Архитектурный принцип:** Zero Hardcoded Credentials (все ключи, узлы и конфигурации монтируются на лету через FastMCP коннекторы из внешних секретов).

### **2\. Функциональная топология и структура компонентов**

Project\_dVPN/  
├── src/  
│   ├── router/  
│   │   ├── \_\_init\_\_.py  
│   │   ├── engine.py          \# Главный цикл роутера и диспетчер каналов  
│   │   ├── health\_check.py    \# Асинхронный Heartbeat-монитор каналов (RTT, Loss, DPI-block)  
│   │   ├── state\_machine.py   \# Стейт-машина состояний каналов (PRIMARY \-\> DEGRADED \-\> FAILOVER)  
│   │   └── tunnel\_adapter.py  \# Абстрактный интерфейс для WireGuard / VLESS / Shadowsocks  
│   └── config/  
│       └── router\_schema.py   \# Pydantic-схема валидации прокси-профилей  
├── tests/  
│   ├── test\_router\_engine.py  
│   ├── test\_health\_check.py  
│   └── test\_state\_machine.py  
└── .ai-loop/policy/  
    ├── protected\_paths.yaml  
    └── risk\_classification.yaml

### **3\. Алгоритм переключения каналов и Стейт-Машина (Fallback Logic)**

Роутер оперирует пулом каналов $C \= \\{c\_1, c\_2, \\dots, c\_n\\}$, отсортированных по приоритету.

       ┌────────────────────────┐  
       │   PRIMARY (Active)     │◄────────┐  
       └───────────┬────────────┘         │  
                   │                      │ RTT & Loss восстановлены  
         RTT \> T1  │ loss \> L1            │  
                   ▼                      │  
       ┌────────────────────────┐         │  
       │   DEGRADED (Warning)   ├─────────┘  
       └───────────┬────────────┘  
                   │ RTT \> T2 OR Timeout (HTTP 502/DPI Reset)  
                   ▼  
       ┌────────────────────────┐  
       │   FAILOVER (Switched)  │ ──► Вызов TunnelAdapter.switch\_to(next\_channel)  
       └────────────────────────┘

#### **Пороговые метрики триггеров:**

> 1. **Health Check Tick ($T\_{tick} \= 1000\\text{ms}$):** Фоновый асинхронный запрос ICMP/HTTP ping к 3 авторитетным эндпоинтам.  
> 2. **Degraded State:** $\\text{RTT} \> 350\\text{ms}$ или $\\text{Packet Loss} \> 5\\%$ за последние 5 тиков.  
> 3. **Failover Switch Event:** $\\text{RTT} \> 1000\\text{ms}$, 3 подряд таймаута соединения или принудительный TCP Reset (DPI блокировка).  
> 4. **Hysteresis Recovery (Защита от фликкеринга):** Обратное переключение на PRIMARY происходит только после $N=10$ последовательных успешных тиков со стабильным RTT.

### **4\. FastMCP Интеграция & Секреты**

Все параметры туннелей (VLESS UUIDs, WireGuard Private Keys, IP-адреса) **запрещено** хранить в коде или локальных текстовых файлах.

* **Инструмент:** FastMCP Сервер mcp-vpn-credentials.  
* **Запрос:**  
  Python  
  \# Безопасное извлечение конфигурации в память контейнера  
  channel\_config \= await mcp\_client.call\_tool(  
      "get\_vpn\_profile",   
      {"tier": "premium", "protocol": "vless"}  
  )

* **Security Guard:** Любая попытка агента записать сырой IP или частный ключ прямо в код src/ мгновенно активирует статус CRITICAL на этапе Commit Gate.

### **5\. Инварианты безопасности (MAX Risk Guardrails)**

> 1. **Защищенные пути (Project\_dVPN/.ai-loop/policy/protected\_paths.yaml):**  
>    YAML  
>    protected\_paths:  
>      \- ".ai-loop/policy/\*\*"  
>      \- "src/config/production\_keys.pem"

> 2. **MAX Risk Rule:**  
>    Субагент Acting Child, работающий над dVPN, не имеет доступа к директории /Supervisor родительской системы Why\_Ai.  
> 3. **Out-of-Band Panic:**  
>    При попытке модификации правил фильтрации системного трафика вне рамок песочницы WorktreeSandbox.py система генерирует Exit Code 10\.

### **6\. Доказательное тестирование (Red-Green TDD & Verification Plan)**

Агент обязать соблюдать правило **Proof of Falsification**:

> 1. **Red Phase (Фаза Фальсификации):** Агент пишет тест test\_fallback\_on\_dpi\_drop(), имитирующий обрыв первичного канала (TCP Reset). Тест **обязан упасть** на старом/пустом коде с фиксацией в failures.jsonl.  
> 2. **Green Phase (Фаза Коррекции):** Агент пишет минимальный код в engine.py, обеспечивающий переключение на резервный канал. Тест становится зеленым.  
> 3. **Reviewed Commit Gate:**  
   * Снятие Preflight SHA-256 Fingerprint.  
   * Прогон через мультимодельный кворум (QuorumReviewer.py).  
   * Финальный 3-Way Merge в основную ветку Project\_dVPN.

### **7\. Метрики для Telemetry Dock (dashboard.html)**

При работе роутера бэкенд транслирует в SSE-канал /api/events/stream следующие структуры данных:

* active\_channel\_id: Идентификатор текущего активного туннеля.  
* channel\_rtt\_ms: Текущая задержка (отображается на графике RTT).  
* failover\_events\_count: Счетчик аварийных переключений.  
* context\_fit\_score: Метрика связности графа AST для модуля engine.py.

### **8\. Пошаговый чек-лист задач для субагента Acting Child**

* \[ \] **Task 1:** Создать структуру папок Project\_dVPN для ‘.../router/’ и инициализировать Pydantic-схемы профилей.  
* \[ \] **Task 2:** Написать falling-тест test\_health\_check\_failure() для проверки определения падения канала.  
* \[ \] **Task 3:** Реализовать асинхронный модуль health\_check.py (HTTP/ICMP pinger).  
* \[ \] **Task 4:** Реализовать стейт-машину state\_machine.py с учетом гистерезиса восстановления.  
* \[ \] **Task 5:** Интегрировать FastMCP-клиент для динамического получения прокси-профилей.  
* \[ \] **Task 6:** Прогнать полный цикл Commit Gate и подтвердить коммит через мультимодельный кворум.