# Architecture

How the app is put together. The README shows the overview (diagram 1); this file has the detail.
Diagrams are written in Mermaid, which GitHub renders directly.

**Colour key used in every diagram**

| Colour | Meaning |
|---|---|
| 🟪 Purple | The driver |
| 🟦 Blue | Runs in the browser (React) |
| 🟩 Green | Runs on our server (Django) |
| 🟧 Orange | Outside services we call |
| ⬜ Grey | Stored data (cache) |
| 🟨 Yellow | Help shown to the driver when something fails |

## 1. System overview

```mermaid
flowchart TB
    driver(["👤 Driver"])

    subgraph browser["🖥️ Browser (Vercel)"]
        ui["React app<br/>form · results · map · slider"]
    end

    tiles["🗺️ OpenFreeMap<br/>map tiles"]

    subgraph server["⚙️ Our server (Render)"]
        direction LR
        api["Django API<br/>POST /api/plan<br/>GET /api/places<br/>GET /api/health"]
        cache[("🗄️ Weather cache<br/>in memory, 1 hour")]
    end

    subgraph outside["🌐 Outside services"]
        direction LR
        ors["🚚 OpenRouteService<br/>truck routes · place search"]
        meteo["🌦️ Open-Meteo<br/>hourly forecasts"]
    end

    driver -->|"① enters trip"| ui
    ui -->|"map background · no key"| tiles
    ui -->|"② trip details as JSON"| api
    api -->|"⑤ routes · risk · heatmap · recommendation"| ui
    api <-->|"reuse if under 1 h old"| cache
    api -->|"③ routes + place search · key stays here"| ors
    api -->|"④ forecasts · 100 points per request"| meteo

    classDef person fill:#ede9fe,stroke:#7c3aed,stroke-width:2px,color:#1f2937
    classDef front fill:#e0f2fe,stroke:#0284c7,stroke-width:2px,color:#1f2937
    classDef back fill:#dcfce7,stroke:#16a34a,stroke-width:2px,color:#1f2937
    classDef ext fill:#ffedd5,stroke:#ea580c,stroke-width:2px,color:#1f2937
    classDef data fill:#f3f4f6,stroke:#6b7280,stroke-width:2px,color:#1f2937
    class driver person
    class ui front
    class api back
    class ors,meteo,tiles ext
    class cache data
    style browser fill:#f0f9ff,stroke:#0284c7,color:#0c4a6e
    style server fill:#f0fdf4,stroke:#16a34a,color:#14532d
    style outside fill:#fff7ed,stroke:#ea580c,color:#7c2d12
```

- The browser only talks to **our API** and the **tile server**. The ORS key never reaches the browser.
- There is **no database**: every plan is calculated fresh; only weather is cached.

## 2. What happens when the driver presses "Plan trip"

```mermaid
sequenceDiagram
    autonumber
    actor D as 👤 Driver
    box rgb(224,242,254) Browser
        participant UI as React app
    end
    box rgb(220,252,231) Our server
        participant API as Django API
    end
    box rgb(255,237,213) Outside services
        participant ORS as OpenRouteService
        participant OM as Open-Meteo
    end

    D->>UI: Fill in trip, press Plan trip
    UI->>API: POST /api/plan (places, departure, load, interval)

    rect rgb(240,253,244)
        Note over API,ORS: Routes
        API->>API: Check input, find origin time zone
        API->>ORS: Fastest truck route
        API->>ORS: Up to 2 detour routes (long trips)
        API->>API: Drop near-duplicate and too-slow routes
    end

    rect rgb(240,249,255)
        Note over API,OM: Weather
        API->>API: Checkpoints + ETAs, pick heatmap squares
        API->>OM: Hourly weather for unique cells (cached, batches of 100)
    end

    rect rgb(254,249,195)
        Note over API: Risk and ranking
        API->>API: Risk per checkpoint, 49 hourly levels per square
        API->>API: Summarise, rank, write the reason
    end

    API-->>UI: Routes, checkpoints, heatmap, recommendation
    UI-->>D: Map, route cards, slider
```

If any step fails, the API sends back a plain message and suggested actions instead (diagram 7).

## 3. Backend modules: who may use whom

```mermaid
flowchart TD
    views["🌐 views.py + serializers.py<br/>HTTP in → JSON out, input checks"]
    service["🧩 service.py · plan_trip()<br/>the only place that knows the order of steps"]

    subgraph pure["🟢 Pure logic (no network)"]
        risk["risk.py<br/>weather → risk level"]
        geo["geo.py<br/>distance · ETAs · checkpoints"]
        routes["routes.py<br/>detours · distinct routes"]
        recommend["recommend.py<br/>summary · ranking · reason"]
        corridor["corridor.py<br/>heatmap squares · hourly levels"]
    end

    subgraph clients["🟠 Clients (network)"]
        ors["clients/ors.py<br/>OpenRouteService"]
        weather["clients/weather.py<br/>Open-Meteo + cache"]
    end

    views -->|"calls"| service
    service -->|"uses"| pure
    service -->|"uses"| clients
    corridor -->|"classifies with"| risk
    recommend -->|"scores with"| risk

    classDef web fill:#e0f2fe,stroke:#0284c7,stroke-width:2px,color:#1f2937
    classDef glue fill:#fef9c3,stroke:#ca8a04,stroke-width:2px,color:#1f2937
    classDef logic fill:#dcfce7,stroke:#16a34a,stroke-width:2px,color:#1f2937
    classDef net fill:#ffedd5,stroke:#ea580c,stroke-width:2px,color:#1f2937
    class views web
    class service glue
    class risk,geo,routes,recommend,corridor logic
    class ors,weather net
    style pure fill:#f0fdf4,stroke:#16a34a,color:#14532d
    style clients fill:#fff7ed,stroke:#ea580c,color:#7c2d12
```

- Arrows point from the module that **imports** to the module it **uses**. Pure modules never import clients or Django.
- Tests never call real APIs: clients are tested with saved sample responses.

## 4. The plan pipeline, and the help offered where it can stop

```mermaid
flowchart TD
    A["① Check input<br/>and departure window"] --> B["② Get up to 3<br/>truck routes"]
    B --> C["③ Checkpoints<br/>and ETAs"]
    C --> D["④ Count weather cells,<br/>size the heatmap"]
    D --> E["⑤ Fetch weather"]
    E --> F["⑥ Risk per checkpoint<br/>and square"]
    F --> G["⑦ Rank and explain"]
    G --> H(["⑧ Send plan to the browser"])

    A -. "time has passed /<br/>beyond 16 days" .-> X1["💡 Leave now ·<br/>Plan for latest date"]
    B -. "no road nearby /<br/>no truck route" .-> X2["💡 Use nearest place ·<br/>Try nearby destination"]
    D -. "too many<br/>checkpoints" .-> X3["💡 Use 25 mi ·<br/>Use 50 mi"]
    E -. "weather down<br/>or busy" .-> X4["💡 Show routes as<br/>'weather unknown' · Try again"]

    classDef step fill:#dcfce7,stroke:#16a34a,stroke-width:2px,color:#1f2937
    classDef done fill:#e0f2fe,stroke:#0284c7,stroke-width:2px,color:#1f2937
    classDef help fill:#fef3c7,stroke:#d97706,stroke-width:2px,color:#1f2937
    class A,B,C,D,E,F,G step
    class H done
    class X1,X2,X3,X4 help
```

## 5. Front end: components and state

```mermaid
flowchart TB
    App["🧠 App · holds all state<br/>form · plan · problem · loading<br/>selected route · slider hour · open popup"]

    subgraph formG["📝 Trip form"]
        direction TB
        Place["PlaceInput ×2<br/>search as you type"] ~~~ Dep["DepartureInput"] ~~~ Load["LoadInput (lb)"] ~~~ Int["IntervalToggle<br/>10 · 25 · 50 mi"]
    end

    subgraph resG["📋 Results panel"]
        direction TB
        Rec["Recommendation<br/>winner + reason"] ~~~ Cards["RouteCard ×3<br/>time · miles · risk"] ~~~ Problem["ProblemPanel<br/>message + buttons"]
    end

    subgraph mapG["🗺️ Map"]
        direction TB
        RL["RouteLayer<br/>coloured segments"] ~~~ CL["CheckpointLayer<br/>dots + popup"] ~~~ HL["HeatmapLayer<br/>coloured squares"]
    end

    subgraph sliderG["⏱️ Time"]
        direction TB
        Slider["HourSlider<br/>0–48 h"] ~~~ Legend["Legend<br/>level names"]
    end

    App -->|"form values"| formG
    App -->|"plan or problem"| resG
    App -->|"routes · selected · hour"| mapG
    App -->|"hour"| sliderG

    api["⚙️ Our API<br/>GET /api/places · POST /api/plan"]
    formG -. "search as you type" .-> api
    App -. "usePlan(): plan trip" .-> api

    classDef state fill:#ede9fe,stroke:#7c3aed,stroke-width:2px,color:#1f2937
    classDef comp fill:#e0f2fe,stroke:#0284c7,stroke-width:2px,color:#1f2937
    classDef endpoint fill:#dcfce7,stroke:#16a34a,stroke-width:2px,color:#1f2937
    class App state
    class Place,Dep,Load,Int,Rec,Cards,Problem,RL,CL,HL,Slider,Legend comp
    class api endpoint
    style formG fill:#f0f9ff,stroke:#0284c7,color:#0c4a6e
    style resG fill:#f0f9ff,stroke:#0284c7,color:#0c4a6e
    style mapG fill:#f0f9ff,stroke:#0284c7,color:#0c4a6e
    style sliderG fill:#f0f9ff,stroke:#0284c7,color:#0c4a6e
```

State lives only in `App` and flows **down** (solid arrows). Components report changes back **up**: picking a route card, moving the slider, editing the form. Dashed arrows are calls to our API.

## 6. Why the heatmap slider is smooth

```mermaid
flowchart LR
    S["⚙️ Server sends each square once<br/>with all 49 hours: h0 … h48"] -->|"once per plan"| M["🎮 Map keeps the squares<br/>on the graphics card"]
    U["👤 Driver drags slider to 17"] -->|"instant"| P["Change one colour rule:<br/>colour by h17"]
    P -->|"no request, no new data"| M
    M -->|"under one frame"| R(["✨ Repainted"])

    classDef back fill:#dcfce7,stroke:#16a34a,stroke-width:2px,color:#1f2937
    classDef front fill:#e0f2fe,stroke:#0284c7,stroke-width:2px,color:#1f2937
    classDef person fill:#ede9fe,stroke:#7c3aed,stroke-width:2px,color:#1f2937
    class S back
    class M,P,R front
    class U person
```

## 7. How failures reach the driver

```mermaid
flowchart LR
    E["⚙️ Something fails<br/>on the server"] -->|"never just 'error'"| J["JSON: plain message<br/>+ list of actions"]
    L["🖥️ Location fails<br/>in the browser"] -->|"handled locally"| PP
    J --> PP["📋 ProblemPanel<br/>form stays filled in"]
    PP -->|"shows"| B1["💡 Use 25 mi"]
    PP -->|"shows"| B2["💡 Try again"]
    PP -->|"shows"| B3["💡 Type a nearby town"]
    B1 -->|"changes one field, re-plans"| plan["POST /api/plan"]
    B2 -->|"same trip, re-plans"| plan

    classDef back fill:#dcfce7,stroke:#16a34a,stroke-width:2px,color:#1f2937
    classDef front fill:#e0f2fe,stroke:#0284c7,stroke-width:2px,color:#1f2937
    classDef help fill:#fef3c7,stroke:#d97706,stroke-width:2px,color:#1f2937
    class E,J,plan back
    class L,PP front
    class B1,B2,B3 help
```

Unknown weather is never shown as Low, and a failure never clears what the driver typed.

## 8. Code conventions (for reviewers and AI tools)

Written so that a reviewer, or an AI assistant helping one, can follow the code quickly and not miss a rule:

- **Every function and every test has a one-line description** of what it does.
- **Where code implements an assumption, a comment cites its number**, e.g. `# #30: shared edge goes to the higher band`. Searching for `#30` finds the rule in the README, the code that implements it, and the test that proves it.
- **Assumption numbers never change.** New ones are added at the end.
- **Test names read as sentences**, e.g. `test_rain_at_0_25_is_high_because_higher_band_wins`, so a failing test explains itself.
- **No comments that repeat the code.** Comments explain *why*, not *what*.
