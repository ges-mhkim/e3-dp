/* 신 환경 빌드의 기본 자료형 크기와 struct pdu_info 레이아웃 확인 (ABI 점검용) */
#include <stdio.h>
#include <stddef.h>
#include <time.h>
#include <drmodule.h>
#include <scan/scan.h>

int main(void)
{
	printf("time_t=%d long=%d ptr=%d\n", (int)sizeof(time_t), (int)sizeof(long), (int)sizeof(void *));
	printf("pdu_info size=%d var_parsed_off=%d mesg_size_off=%d requestid_off=%d\n",
	       (int)sizeof(struct pdu_info), (int)offsetof(struct pdu_info, pdu_var_parsed),
	       (int)offsetof(struct pdu_info, pdu_mesg_size), (int)offsetof(struct pdu_info, pdu_requestid));
	return 0;
}
