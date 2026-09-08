@echo off
REM Agent Reach wrapper - sets PATH so agent-reach and all tools are discoverable
set PATH=E:\CCProject\agent_reach\gh-cli\bin;E:\CCProject\agent_reach\.agent-reach-venv\Scripts;C:\Users\zhengjingyi\.workbuddy\binaries\node\versions\22.22.2;%PATH%
opencli daemon start >nul 2>&1
E:\CCProject\agent_reach\.agent-reach-venv\Scripts\agent-reach.exe %*
