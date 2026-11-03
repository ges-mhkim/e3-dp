#!/usr/bin/env bash
# ==============================================================================
# dev_wsl.sh: WSL2에서 QEMU user-mode + chroot 기반 armhf 개발/빌드 환경 스크립트
#
# - 대상 장치: NanoPi NEO (Allwinner H3, armhf)
# - 대상 OS: Debian 13 (Trixie) armhf (GCC 14.2)
# - 소스 공유: 호스트의 e3dp 디렉토리를 chroot 내 /home/e3dp 에 바인드 마운트
#              -> Makefile의 HOME_DIR=/home/e3dp/e3dp.2.1 과 정확히 일치
# ==============================================================================

set -euo pipefail

# 스크립트 위치 및 경로 설정
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"
OS_DIR="$(cd "$SCRIPT_DIR/../os_new" 2>/dev/null && pwd || echo "$SCRIPT_DIR/../os_new")"
IMAGE_PATH="${IMAGE_PATH:-$OS_DIR/e3dp-poc-debian13-armhf.img}"
MOUNT_DIR="${MOUNT_DIR:-/mnt/e3dp_armhf_root}"
PART_OFFSET=1048576  # 2048 sector * 512 bytes = 1MiB (파티션 1 시작 위치)

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# 선언된 경로와 파일 확인 (MOUNT_DIR은 마운트 시 자동 생성)
check_paths() {
    local name path
    local invalid=0
    for name in SCRIPT_DIR PROJECT_DIR OS_DIR IMAGE_PATH MOUNT_DIR; do
        path="${!name}"
        if { [ "$name" = IMAGE_PATH ] && [ ! -f "$path" ]; } ||
           { [ "$name" != IMAGE_PATH ] && [ "$name" != MOUNT_DIR ] && [ ! -d "$path" ]; } ||
           { [ "$name" = MOUNT_DIR ] && { [ -e "$path" ] || [ -L "$path" ]; } && [ ! -d "$path" ]; }; then
            printf '%b[ERROR] %s 경로 또는 파일을 확인해 주세요: %s%b\n' "$RED" "$name" "$path" "$NC" >&2
            invalid=1
        fi
    done
    if [ "$invalid" -ne 0 ]; then
        printf '스크립트 상단의 경로 설정을 실제 위치에 맞게 수정해 주세요: %s\n' "$SCRIPT_DIR/dev_wsl.sh" >&2
        printf 'IMAGE_PATH와 MOUNT_DIR은 환경 변수로도 지정할 수 있습니다.\n' >&2
        exit 1
    fi
}

# root 권한 자동 획득
ensure_root() {
    case "${1:-enter}" in
        enter|build|exec|check|mount) check_paths ;;
    esac
    if [ "$EUID" -ne 0 ]; then
        echo -e "${YELLOW}[!] root 권한이 필요합니다. sudo 로 재실행합니다...${NC}"
        exec sudo IMAGE_PATH="$IMAGE_PATH" MOUNT_DIR="$MOUNT_DIR" "$0" "$@"
    fi
}

# binfmt_misc 및 qemu-arm-static 사전 점검
check_prerequisites() {
    if ! command -v qemu-arm-static >/dev/null 2>&1; then
        echo -e "${RED}[ERROR] qemu-arm-static 이 설치되어 있지 않습니다.${NC}"
        echo "다음 명령으로 설치해 주세요: sudo apt-get update && sudo apt-get install -y qemu-user-static binfmt-support"
        exit 1
    fi

    # binfmt_misc 마운트 확인 및 시도
    if [ ! -d /proc/sys/fs/binfmt_misc ]; then
        modprobe binfmt_misc 2>/dev/null || true
    fi
    if ! grep -q binfmt_misc /proc/mounts 2>/dev/null; then
        mount -t binfmt_misc binfmt_misc /proc/sys/fs/binfmt_misc 2>/dev/null || true
    fi

    # binfmt 활성화
    if [ -x /usr/sbin/update-binfmts ]; then
        update-binfmts --enable qemu-arm 2>/dev/null || update-binfmts --enable 2>/dev/null || true
    fi

    if [ ! -f "$IMAGE_PATH" ]; then
        echo -e "${RED}[ERROR] 대상 이미지 파일을 찾을 수 없습니다: $IMAGE_PATH${NC}"
        exit 1
    fi
}

# 마운트 여부 확인
is_mounted() {
    mountpoint -q "$MOUNT_DIR" 2>/dev/null
}

# chroot 환경 마운트
mount_env() {
    if is_mounted; then
        return 0
    fi

    echo -e "${CYAN}[*] armhf chroot 환경 마운트 중...${NC}"
    mkdir -p "$MOUNT_DIR"

    # 1. ext4 이미지 loop 마운트 (파티션 1)
    mount -o loop,offset=$PART_OFFSET "$IMAGE_PATH" "$MOUNT_DIR"

    # 2. qemu-arm-static 바이너리 복사 (chroot 내 armhf 바이너리 실행용)
    mkdir -p "$MOUNT_DIR/usr/bin"
    cp -f /usr/bin/qemu-arm-static "$MOUNT_DIR/usr/bin/"
    chmod +x "$MOUNT_DIR/usr/bin/qemu-arm-static"

    # 3. 필수 가상 파일시스템 바인드 마운트
    mount --bind /proc "$MOUNT_DIR/proc"
    mount --bind /sys "$MOUNT_DIR/sys"
    mount --bind /dev "$MOUNT_DIR/dev"
    mount --bind /dev/pts "$MOUNT_DIR/dev/pts"

    # 4. DNS 설정 전달
    if [ -f /etc/resolv.conf ]; then
        cp -L /etc/resolv.conf "$MOUNT_DIR/etc/resolv.conf" 2>/dev/null || true
    fi

    # 5. 소스 코드 바인드 마운트
    #    호스트 e3dp 디렉토리를 chroot 내 /home/e3dp 에 마운트하여
    #    Makefile의 HOME_DIR=/home/e3dp/e3dp.2.1 구조를 그대로 충족시킵니다.
    mkdir -p "$MOUNT_DIR/home/e3dp"
    mount --bind "$PROJECT_DIR" "$MOUNT_DIR/home/e3dp"

    echo -e "${GREEN}[+] 마운트 완료: $MOUNT_DIR${NC}"
}

# chroot 환경 언마운트
umount_env() {
    if ! is_mounted; then
        echo -e "${YELLOW}[*] 이미 마운트되어 있지 않습니다.${NC}"
        return 0
    fi

    echo -e "${CYAN}[*] armhf chroot 환경 정리(언마운트) 중...${NC}"

    # 안전하게 역순 언마운트
    targets=(
        "$MOUNT_DIR/home/e3dp"
        "$MOUNT_DIR/dev/pts"
        "$MOUNT_DIR/dev"
        "$MOUNT_DIR/proc"
        "$MOUNT_DIR/sys"
        "$MOUNT_DIR"
    )

    for target in "${targets[@]}"; do
        if mountpoint -q "$target" 2>/dev/null; then
            umount -l "$target" 2>/dev/null || true
        fi
    done

    # 남은 마운트 포인트 확인
    if is_mounted; then
        umount -l "$MOUNT_DIR" 2>/dev/null || true
    fi

    echo -e "${GREEN}[+] 언마운트 완료.${NC}"
}

# chroot 셸 진입
enter_env() {
    check_prerequisites
    mount_env

    echo -e "${GREEN}================================================================${NC}"
    echo -e "${GREEN} Debian 13 (Trixie) armhf QEMU chroot 환경에 진입합니다.${NC}"
    echo -e " - 작업 디렉토리: ${CYAN}/home/e3dp/e3dp.2.1${NC}"
    echo -e " - 종료 시: ${YELLOW}exit${NC} (마운트는 유지되므로 재진입이 빠릅니다)"
    echo -e " - 마운트 해제: 호스트에서 ${YELLOW}./dev_wsl.sh umount${NC}"
    echo -e "${GREEN}================================================================${NC}"

    chroot "$MOUNT_DIR" /usr/bin/env \
        HOME=/root \
        TERM="$TERM" \
        PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" \
        PS1='\[\033[01;32m\][armhf-chroot]\[\033[00m\]:\[\033[01;34m\]\w\[\033[00m\]\$ ' \
        /bin/bash --login -c "cd /home/e3dp/e3dp.2.1 && exec /bin/bash -i"
}

# 직접 빌드 명령 실행
build_env() {
    check_prerequisites
    mount_env

    echo -e "${CYAN}[*] chroot 내부에서 make 실행 중... (인자: $*)${NC}"
    chroot "$MOUNT_DIR" /usr/bin/env \
        PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" \
        /bin/bash -c "cd /home/e3dp/e3dp.2.1 && make $*"
}

# 임의의 명령을 chroot 내부에서 실행
exec_cmd() {
    check_prerequisites
    mount_env

    chroot "$MOUNT_DIR" /usr/bin/env \
        PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" \
        /bin/bash -c "cd /home/e3dp/e3dp.2.1 && $*"
}

# armhf 환경 및 컴파일러/구조체 정렬 검증
check_env() {
    check_prerequisites
    mount_env

    echo -e "${CYAN}================================================================${NC}"
    echo -e "${CYAN} armhf 에뮬레이션 및 컴파일러 / 구조체 정렬 검증${NC}"
    echo -e "${CYAN}================================================================${NC}"

    # 임시 C 테스트 코드 작성 및 실행
    chroot "$MOUNT_DIR" /bin/bash <<'EOF'
set -e
cat << 'SRC' > /tmp/check_armhf.c
#include <stdio.h>
#include <stdint.h>
#include <time.h>
#include <stddef.h>

struct TestAlign {
    char a;
    long long b;
    int c;
};

int main(void) {
    printf("=== 시스템 및 컴파일러 정보 ===\n");
#if defined(__arm__)
    printf("[OK] Architecture: ARM 32-bit (__arm__)\n");
#else
    printf("[FAIL] Not ARM!\n");
#endif

#if defined(__ARM_PCS_VFP)
    printf("[OK] ABI: armhf (Hard Float VFP)\n");
#else
    printf("[INFO] ABI: armel (Soft Float)\n");
#endif

    printf("\n=== 기본 타입 크기 (sizeof) ===\n");
    printf("sizeof(void*)      : %zu bytes (기대값: 4)\n", sizeof(void*));
    printf("sizeof(long)       : %zu bytes (기대값: 4)\n", sizeof(long));
    printf("sizeof(long long)  : %zu bytes (기대값: 8)\n", sizeof(long long));
    printf("sizeof(time_t)     : %zu bytes (Debian 13 Trixie Y2038 대응: 8)\n", sizeof(time_t));

    printf("\n=== 구조체 정렬 및 패딩 (Struct Alignment) ===\n");
    printf("struct TestAlign {\n    char a;\n    long long b;\n    int c;\n};\n");
    printf("sizeof(struct TestAlign): %zu bytes\n", sizeof(struct TestAlign));
    printf("offsetof(a): %zu, offsetof(b): %zu, offsetof(c): %zu\n",
           offsetof(struct TestAlign, a),
           offsetof(struct TestAlign, b),
           offsetof(struct TestAlign, c));
    return 0;
}
SRC

echo -e "\n1. GCC 컴파일러 버전:"
gcc --version | head -1
echo "   Target: $(gcc -dumpmachine)"

echo -e "\n2. 테스트 프로그램 빌드 및 실행:"
gcc -O2 /tmp/check_armhf.c -o /tmp/check_armhf
/tmp/check_armhf
rm -f /tmp/check_armhf.c /tmp/check_armhf
EOF
}

# 마운트 상태 확인
status_env() {
    echo -e "${CYAN}=== 마운트 상태 점검 ===${NC}"
    echo "이미지 경로: $IMAGE_PATH"
    echo "마운트 디렉토리: $MOUNT_DIR"
    echo ""
    if is_mounted; then
        echo -e "상태: ${GREEN}마운트됨 (Active)${NC}"
        echo "세부 마운트 목록:"
        mount | grep "$MOUNT_DIR" || true
    else
        echo -e "상태: ${YELLOW}마운트 안 됨 (Inactive)${NC}"
    fi
}

# 도움말
show_usage() {
    echo "사용법: $0 [명령] [추가 옵션...]"
    echo ""
    echo "명령 목록:"
    echo "  enter (기본값)   armhf chroot 셸(/bin/bash)로 진입 (기본 위치: /home/e3dp/e3dp.2.1)"
    echo "  build [make인자] chroot 내부에서 바로 make 실행 (예: build clean, build -j4)"
    echo "  exec \"<명령>\"     chroot 내부(/home/e3dp/e3dp.2.1)에서 임의 명령 1회 실행"
    echo "  check            GCC 14.2 버전, armhf 아키텍처 및 구조체 크기/정렬 즉석 검증"
    echo "  mount            chroot 환경 마운트만 수행"
    echo "  umount           chroot 환경 언마운트 및 정리"
    echo "  status           현재 마운트 상태 확인"
    echo "  help, --help, -h 이 도움말 표시"
    echo ""
    echo "예시:"
    echo "  $0               # chroot 셸 진입"
    echo "  $0 build         # 바로 make 빌드"
    echo "  $0 build clean   # make clean 실행"
    echo "  $0 check         # armhf 및 구조체 크기 검증"
    echo "  $0 umount        # 작업 완료 후 언마운트"
}

# 메인 실행 분기
CMD="${1:-enter}"
shift || true

case "$CMD" in
    help|--help|-h)
        show_usage
        ;;
    status)
        status_env
        ;;
    enter)
        ensure_root "$CMD" "$@"
        enter_env
        ;;
    build)
        ensure_root "$CMD" "$@"
        build_env "$@"
        ;;
    exec)
        ensure_root "$CMD" "$@"
        exec_cmd "$@"
        ;;
    check)
        ensure_root "$CMD" "$@"
        check_env
        ;;
    mount)
        ensure_root "$CMD" "$@"
        check_prerequisites
        mount_env
        ;;
    umount|down|stop)
        ensure_root "$CMD" "$@"
        umount_env
        ;;
    *)
        echo -e "${RED}[ERROR] 알 수 없는 명령: $CMD${NC}"
        show_usage
        exit 1
        ;;
esac
