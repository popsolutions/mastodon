COMMON_OVERLAYS += nginx ruby nodejs
COMMON_CONF += nginx ruby nodejs redis

include $(FAB_PATH)/common/mk/turnkey.mk
include $(FAB_PATH)/common/mk/turnkey/pgsql.mk
