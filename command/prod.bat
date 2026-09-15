@echo off
REM ===== 获取当天日期 =====
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set datetime=%%I
set TODAY=%datetime:~0,4%-%datetime:~4,2%-%datetime:~6,2%

REM ===== 获取前两天的日期（借用 Python 计算） =====
for /f %%I in ('python -c "from datetime import datetime, timedelta; print((datetime.now() - timedelta(days=10)).strftime('%%Y-%%m-%%d'))"') do set DAY_BEFORE_2=%%I

REM ===== 切换到项目根目录 =====
cd /d C:\Users\anycubic\Documents\agent_reach-main

REM ===== 创建日志目录（如果不存在） =====
if not exist "logs" mkdir logs

REM ===== 定义日志文件路径 =====
set LOG_FILE=logs\task_%TODAY%.log

echo [%TODAY% %time%] ===== 任务开始执行 ===== >> "%LOG_FILE%"
echo [%TODAY% %time%] TODAY=%TODAY%, DAY_BEFORE_2=%DAY_BEFORE_2% >> "%LOG_FILE%"

REM ===== 1. IG: 账号级 =====
echo [%TODAY% %time%] 执行 fetch_account_overview.py ... >> "%LOG_FILE%"
python C:\Users\anycubic\Documents\agent_reach-main\scripts\instagram\fetch_account_overview.py --start-date %DAY_BEFORE_2% --end-date %TODAY% >> "%LOG_FILE%" 2>&1
timeout /t 60 /nobreak >nul

REM ===== 2. IG: 帖子级 =====
echo [%TODAY% %time%] 执行 fetch_instagram_posts.py ... >> "%LOG_FILE%"
python C:\Users\anycubic\Documents\agent_reach-main\scripts\instagram\fetch_instagram_posts.py --start-date %DAY_BEFORE_2% --end-date %TODAY% >> "%LOG_FILE%" 2>&1
timeout /t 60 /nobreak >nul

REM ===== 3. Twitter: 帖子级（无日期参数） =====
echo [%TODAY% %time%] 执行 fetch_anycubic3dprint_analytics.py ... >> "%LOG_FILE%"
python C:\Users\anycubic\Documents\agent_reach-main\scripts\twitter\fetch_anycubic3dprint_analytics.py --start-date %DAY_BEFORE_2% --end-date %TODAY% >> "%LOG_FILE%" 2>&1
timeout /t 60 /nobreak >nul

REM ===== 4. Twitter: 账号级 =====
echo [%TODAY% %time%] 执行 fetch_anycubic3dprint_page_analytics.py ... >> "%LOG_FILE%"
python C:\Users\anycubic\Documents\agent_reach-main\scripts\twitter\fetch_anycubic3dprint_page_analytics.py --start-date %DAY_BEFORE_2% --end-date %TODAY% >> "%LOG_FILE%" 2>&1
timeout /t 60 /nobreak >nul

REM ===== 5. Twitter: 视频总览层级 =====
echo [%TODAY% %time%] 执行 fetch_anycubic3dprint_video_analytics.py ... >> "%LOG_FILE%"
python C:\Users\anycubic\Documents\agent_reach-main\scripts\twitter\fetch_anycubic3dprint_video_analytics.py --start-date %DAY_BEFORE_2% --end-date %TODAY% >> "%LOG_FILE%" 2>&1

echo [%TODAY% %time%] ===== 任务执行完毕 ===== >> "%LOG_FILE%"
echo. >> "%LOG_FILE%"