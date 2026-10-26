/* 커버리지 계측 빌드용 LD_PRELOAD 라이브러리.
 * DP 서버는 SIGTERM 핸들러가 없어 kill 시 gcov 데이터(.gcda)가 기록되지 않는다.
 * 이 라이브러리는 로드될 때 SIGTERM 에서 exit(0) 하도록 설정해 종료 시 gcov 데이터를 기록하게 한다.
 */
#include <signal.h>
#include <stdlib.h>

static void on_term(int sig)
{
	(void)sig;
	exit(0);
}

__attribute__((constructor)) static void gcovflush_init(void)
{
	struct sigaction sa;

	sa.sa_handler = on_term;
	sigemptyset(&sa.sa_mask);
	sa.sa_flags = 0;
	sigaction(SIGTERM, &sa, 0);
}
