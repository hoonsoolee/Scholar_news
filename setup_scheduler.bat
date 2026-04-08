@echo off
echo Scholar News 자동 실행 스케줄러 등록 중...

:: 아침 7시 실행
schtasks /create /tn "ScholarNews_Morning" /tr "python D:\Scholar_news\scholar_news.py" /sc daily /st 07:00 /f

:: 저녁 7시 실행
schtasks /create /tn "ScholarNews_Evening" /tr "python D:\Scholar_news\scholar_news.py" /sc daily /st 19:00 /f

echo.
echo 완료! 매일 오전 7시 / 오후 7시에 자동 실행됩니다.
pause
