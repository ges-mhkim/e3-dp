mount -t cifs //10.10.1.20/e3dp /home/e3dp -o username=dev,password=ges000,uid=e3dp,gid=e3dp,file_mode=0755,dir_mode=0755,vers=3.0



## 폴더
- `e3dp/e3dp.2.1` 소스
- `docs/` 문서
- `tasks/` 작업 목록

## Task 관리
- 위치: `tasks/`
- 파일명: `NNN_task_작업제목.md`, 완료 시 `NNN_task_작업제목_done.md`로 변경
- 체크리스트 형식. 새 세션 AI가 이어서 작업할 수 있게 작성.
- 문체: 수식어·장황함 금지, 핵심만.
- 상세 규칙·템플릿: `CLAUDE.md`
