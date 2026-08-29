# Mairon Architecture

## Project Vision

Mairon is a local-first personal AI assistant designed to run continuously from a Raspberry Pi 5.

The Raspberry Pi is Mairon's permanent core: its heart, ears, and mouthpiece. It should remain available even when other devices, including the main desktop PC, are powered off.

Mairon should be capable of natural conversation, remembering useful context, developing a consistent personality, controlling approved devices, accessing internet services when required, and delegating demanding tasks to more powerful systems.

The long-term goal is for Mairon to feel like one continuous assistant regardless of whether it is being accessed through a bedroom microphone, terminal, desktop, or mobile phone.


---

## High-Level Architecture

```text
                         USER
                          │
             ┌────────────┴─────────────┐
             │                          │
           Voice                    Text / App
             │                          │
             └────────────┬─────────────┘
                          ▼
                ┌───────────────────┐
                │  Raspberry Pi 5   │
                │    MAIRON CORE    │
                │                   │
                │ • Conversation    │
                │ • Personality     │
                │ • Memory          │
                │ • Permissions     │
                │ • Task routing    │
                │ • Tool registry   │
                │ • Wake word       │
                │ • Speech-to-text  │
                │ • Text-to-speech  │
                └─────────┬─────────┘
                          │
                    Task Router
                          │
       ┌──────────────────┼───────────────────┐
       │                  │                   │
       ▼                  ▼                   ▼
   PI / LOCAL         DESKTOP PC          CLOUD AI
   PROCESSING         COMPUTE NODE         PROVIDER
       │                  │                   │
 Lightweight AI       Powerful local       OpenAI /
 General chat         AI models            Claude /
 Simple reasoning     RTX GPU compute      future APIs
 Device control       File processing
 Internet tools       Heavy workloads
       │                  │                   │
       └──────────────────┴───────────────────┘
                          │
                          ▼
                       RESULT
                          │
                          ▼
                    MAIRON CORE
                          │
                          ▼
                        USER
```


---

# Core Principles

## 1. The Raspberry Pi is Mairon's Core

Mairon must continue functioning while the desktop PC is completely powered off.

The Raspberry Pi should eventually manage:

- conversation
- personality
- persistent memory
- task routing
- permissions
- tool execution
- device control
- internet/API access
- wake-word detection
- speech-to-text
- text-to-speech
- communication with other Mairon devices


## 2. Local First

Personal information should remain local whenever practical.

A cloud AI service should not automatically receive every conversation or piece of personal information.

Mairon should prefer:

```text
Pi processing
      ↓
Powerful local PC processing
      ↓
Cloud processing
```

depending on the requirements of the task.


## 3. The AI Model is Not Mairon

Mairon's identity must remain separate from whichever AI model is being used.

```text
Mairon
  │
  ├── Personality
  ├── Memory
  ├── Permissions
  ├── Tools
  ├── Preferences
  └── Conversation context
          │
          ▼
     AI Provider
          │
     ┌────┼────┐
     ▼    ▼    ▼
   Local  PC  Cloud
```

Changing from one model to another should not reset Mairon's personality or memories.


## 4. Dynamic Task Routing

Mairon should determine the cheapest, safest, and most appropriate place to execute a task.

Example:

```text
User request
     │
     ▼
Can the Pi handle it?
     │
 ┌───┴───┐
 │ YES   │ NO
 ▼       ▼
Pi      Does it require powerful
        private/local processing?
              │
          ┌───┴───┐
          │ YES   │ NO
          ▼       ▼
       Desktop   Cloud may
         PC      be considered
```

Cloud processing should only occur when permitted.


---

# Example Task Routing

## General Knowledge

```text
"What muscles does an incline dumbbell press work?"

User
 ↓
Pi
 ↓
Local AI
 ↓
Answer
```

The desktop PC should remain off.


## Internet Information

```text
"How long will it take me to drive to uni today?"

User
 ↓
Pi local AI
 ↓
Maps / traffic tool
 ↓
Live traffic information
 ↓
Local AI interprets result
 ↓
Answer
```

Internet access does not automatically require a cloud AI model.


## Smart Device Control

```text
"Turn on my PS5."

User
 ↓
Pi
 ↓
Mairon permissions
 ↓
PS5 control tool
 ↓
PS5 powers on
```

The desktop PC is unnecessary.


## Heavy Private Task

```text
"Analyse this private 80-page document locally."

User
 ↓
Pi
 ↓
Task considered too demanding for Pi
 ↓
Desktop currently offline
 ↓
Wake-on-LAN
 ↓
Desktop boots
 ↓
Mairon Desktop Agent connects
 ↓
Local AI uses desktop GPU
 ↓
Document processed
 ↓
Result returned to Pi
 ↓
Result given to user
 ↓
Desktop may safely shut down
```


## Complex Cloud Task

```text
"Perform extensive research on this topic."

User
 ↓
Pi
 ↓
Task Router
 ↓
Cloud use permitted?
 ↓
Cloud AI / internet research
 ↓
Result
 ↓
Mairon
 ↓
User
```

Only information necessary for that request should be sent externally.


---

# Internet Access

Local AI does not mean offline AI.

Mairon should be capable of accessing internet services through controlled tools.

Examples:

```text
web_search(query)
get_weather(location)
get_route(origin, destination)
get_sports_information(...)
get_calendar_events(...)
get_current_news(...)
```

The local AI reasons about which tool is required.

The tool retrieves real-world information.

Mairon then interprets the result.

The AI model should not receive unrestricted access to the operating system or internet when a limited tool can accomplish the task.


---

# Tool Security

AI models must never have unrestricted shell or system access.

Instead, Mairon exposes approved tools.

Example:

```text
Allowed:

launch_application("minecraft")
wake_desktop()
shutdown_desktop()
turn_light("desk", "off")
get_cpu_temperature()
get_route("home", "uni")


Not allowed:

execute_arbitrary_shell_command(...)
```

The AI may request that a tool be executed.

Mairon Core decides whether execution is permitted.


---

# Permissions

Different actions should have different authority levels.

Possible permission categories:

```text
READ
CONTROL
COMPUTE
FILES
SENSITIVE
ADMIN
```

Examples:

```text
Check PC temperature      → READ

Turn desk lights off      → CONTROL

Wake desktop for AI job   → COMPUTE

Read personal documents   → FILES

Access private memory     → SENSITIVE

Modify Mairon security    → ADMIN
```

Sensitive or destructive actions may require additional confirmation.


---

# Desktop PC Role

The desktop PC is not Mairon's core.

It is a powerful compute and capability node.

Eventually it will run a Mairon Desktop Agent capable of approved operations such as:

- running large local AI models
- GPU-intensive processing
- approved file access
- launching applications
- PC telemetry
- executing computational jobs
- returning results to the Pi

The Pi should be capable of waking the desktop through Wake-on-LAN when required.


## Safe Automatic Shutdown

Mairon must remember why the PC is running.

Example:

```text
PC online
started_by_mairon = true
active_mairon_jobs = 1
```

When the job completes:

```text
Any remaining jobs?
        ↓
       No
        ↓
Was PC started by Mairon?
        ↓
       Yes
        ↓
Is someone actively using PC?
        ↓
       No
        ↓
Shutdown permitted
```

Mairon must not shut down a PC that the user was already using.


---

# Memory and Personality

Mairon should maintain persistent local memory.

Possible information includes:

- preferences
- commonly used devices
- routines
- conversations worth remembering
- user-defined facts
- aliases such as "uni", "gym", or "work"
- personality characteristics developed through interaction

Memory should initially use a simple local database such as SQLite.

The system should distinguish between temporary conversation context and information worth storing long-term.


## Personality

Mairon should develop a consistent personality rather than behaving like a generic assistant.

Desired characteristics include:

- natural conversation
- dry humour
- banter
- familiarity with the user
- ability to adapt gradually through interaction

However, consequential situations involving safety, security, privacy, or destructive actions should override humour and prioritise clear communication.


---

# AI Providers

Mairon should use a provider-independent AI interface.

```text
                    Mairon
                       │
                AI Provider Layer
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
       Pi Local     PC Local      Cloud
        Model        Model        Model
```

Potential implementations may include:

```text
Pi:
Small lightweight local model

Desktop:
Ollama / llama.cpp / other local inference
RTX GPU accelerated models

Cloud:
OpenAI
Anthropic Claude
Other future providers
```

Mairon's core code should not depend permanently on one provider.


---

# Voice Architecture

Eventually the Raspberry Pi will act as Mairon's primary voice interface.

```text
Microphone
    │
    ▼
Wake-word detection
    │
"Mairon"
    │
    ▼
Speech-to-text
    │
    ▼
Mairon Core
    │
    ▼
AI / Tool / Task
    │
    ▼
Response
    │
    ▼
Text-to-speech
    │
    ▼
Speaker
```

Voice components should preferably support local processing where practical.


---

# Remote / Mobile Access

A future mobile application should connect securely to the same Mairon Core.

```text
HOME

Voice
 │
 ▼
Pi


REMOTE

Phone
 │
 ▼
Internet
 │
 ▼
Encrypted authenticated connection
 │
 ▼
Pi
```

The phone is another interface to Mairon, not another independent instance of Mairon.

The Pi should remain the central coordinator.


## Example Remote Workflow

```text
User is overseas
      │
      ▼
Phone:
"Process this using my PC at home."
      │
      ▼
Secure connection
      │
      ▼
Mairon Pi
      │
      ▼
Wake desktop
      │
      ▼
Desktop Agent
      │
      ▼
Perform task
      │
      ▼
Return result
      │
      ▼
Pi
      │
      ▼
Phone
      │
      ▼
Safely shut desktop down
```

The desktop should never require direct exposure to the public internet.


---

# Future Interfaces

Mairon may eventually support multiple interfaces:

```text
Terminal ─────────┐
Bedroom Voice ────┤
Phone App ────────┤
Desktop UI ───────┼──► MAIRON CORE
Web Interface ────┤
Other Rooms ──────┤
Wearables ────────┘
```

All interfaces should share the same:

- memory
- personality
- permissions
- tools
- task system
- AI routing


---

# Current Development Strategy

Mairon is initially being developed on Windows because it provides the fastest environment for building and testing the software.

Development should avoid unnecessary dependence on Windows so that Mairon Core can later move to the Raspberry Pi.

Initial milestones:

```text
Terminal conversation
        ↓
AI provider abstraction
        ↓
Basic personality
        ↓
Conversation context
        ↓
Tool system
        ↓
Persistent local memory
        ↓
Desktop Agent
        ↓
Local AI
        ↓
Raspberry Pi migration
        ↓
Voice
        ↓
Home/device integration
        ↓
Secure remote access
        ↓
Mobile application
```

---

# Long-Term Goal

Mairon should eventually operate as an always-available, local-first personal computing assistant.

The system should be capable of:

- talking naturally with the user
- remembering useful information
- developing a consistent personality
- controlling approved devices
- using live internet information
- operating while the desktop is powered off
- waking powerful computers when additional compute is required
- processing sensitive tasks locally
- selectively using cloud AI for demanding workloads
- safely shutting down resources it started
- working through voice, desktop, and mobile interfaces
- remaining secure while accessible remotely

The Raspberry Pi remains the permanent core of the system.

Everything else is a resource Mairon may use.