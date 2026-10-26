/* PDU 파서 단독 호출 하니스: config_handler.c의 DrScan__pdu_decode 루프를 그대로 재현해 단계별로 출력한다.
 * 사용: pdutest <hex>   (보드에서 e3dp.2.1 의 include/lib 로 컴파일. tests/tools/board.py 의 build_pdutest 참조)
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <drmodule.h>
#include <scan/scan.h>
#include <nelite.h>

int main(int argc, char **argv)
{
	unsigned char buf[2048];
	int len = 0, i, ret, count = 0, osize;
	struct pdu_info pdu;
	struct variable_node var;
	oid name[PDU_MAX_OID];
	int nlen;

	if (argc < 2) return 2;
	for (i = 0; argv[1][i] && argv[1][i + 1]; i += 2) {
		unsigned int b;
		sscanf(argv[1] + i, "%2x", &b);
		buf[len++] = (unsigned char)b;
	}
	printf("input len=%d\n", len);
	osize = oidlen(ev_rt__stationid_oid);
	printf("osize=%d\n", osize);

	pdu_parse_init(&pdu, buf, len);
	ret = pdu_parse_header(&pdu, &var);
	printf("header ret=%d mesg_size=%d\n", ret, pdu.pdu_mesg_size);

	for (i = 0; pdu.pdu_var_parsed == FALSE && i < 20; i++) {
		ret = pdu_parse_body(NULL, &pdu, NULL, &var);
		printf("body[%d] ret=%d mesg_size=%d parsed=%d valid=%d\n", i, ret, pdu.pdu_mesg_size,
		       pdu.pdu_var_parsed, pdu_parse_isValid(&var));
		if (ret == PDU_NOERROR) {
			long v = pdu_var_getInteger(&var);
			pdu_var_GetName(&var, (oid **)&name);
			nlen = pdu_var_getLength(&var);
			printf("  name_len=%d value=%ld arcs:", nlen, v);
			{ int k; for (k = 0; k < nlen; k++) printf(" %lu", (unsigned long)name[k]); }
			printf("\n  compare(value_oid,%d)=%d\n", osize, compare_oid(name, nlen, ev_rt__value_oid, osize));
			count++;
		}
	}
	printf("done count=%d\n", count);
	return 0;
}
