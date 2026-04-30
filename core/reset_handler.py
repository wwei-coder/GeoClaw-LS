import os
import shutil
import time
from utils.logger import logger
from core.config import FINGERPRINT_PATH, BASE_DIR, DB_PATH

RESET_FLAG_FILE = os.path.join(BASE_DIR, ".need_reset")
VECTOR_DB_DIR = os.path.join(BASE_DIR, "vector_db")

def _retry_io(action, attempts=3, delay=0.4):
    last_error = None
    for i in range(max(1, attempts)):
        try:
            action()
            return True, None
        except Exception as e:
            last_error = e
            if i < attempts - 1:
                time.sleep(delay * (i + 1))
    return False, last_error

def mark_for_reset():
    """Create a flag file to indicate a reset is needed on next startup."""
    with open(RESET_FLAG_FILE, "w") as f:
        f.write("reset_pending")
    logger.warning("⚠️  已标记为待重置。请重启程序以生效。")

def perform_reset_if_needed():
    """Check for reset flag and delete vector_db if found."""
    if os.path.exists(RESET_FLAG_FILE):
        logger.info("🔄 检测到重置标记，正在执行清理...")
        reset_ok = True
        
        # 1. Delete vector_db folder
        if os.path.exists(VECTOR_DB_DIR):
            removed, remove_err = _retry_io(lambda: shutil.rmtree(VECTOR_DB_DIR), attempts=3, delay=0.6)
            if removed:
                logger.info(f"✅ 已删除向量库目录: {VECTOR_DB_DIR}")
            else:
                logger.error(f"❌ 删除向量库目录失败: {remove_err}")
                trash_name = f"{VECTOR_DB_DIR}_trash_{int(time.time())}"
                renamed, rename_err = _retry_io(lambda: os.rename(VECTOR_DB_DIR, trash_name), attempts=2, delay=0.4)
                if renamed:
                    logger.warning(f"⚠️  无法删除，已重命名为: {trash_name}")
                else:
                    logger.error(f"❌ 重命名也失败了: {rename_err}")
                    reset_ok = False

        # 2. Delete SQLite memory DB files
        for db_file in (DB_PATH, f"{DB_PATH}-wal", f"{DB_PATH}-shm"):
            if os.path.exists(db_file):
                removed, remove_err = _retry_io(lambda: os.remove(db_file), attempts=3, delay=0.4)
                if removed:
                    logger.info(f"✅ 已删除数据库文件: {db_file}")
                else:
                    logger.error(f"❌ 删除数据库文件失败: {db_file}, {remove_err}")
                    reset_ok = False

        # 3. Delete fingerprint to force rebuild
        if os.path.exists(FINGERPRINT_PATH):
            try:
                os.remove(FINGERPRINT_PATH)
                logger.info(f"✅ 已删除指纹文件: {FINGERPRINT_PATH}")
            except Exception as e:
                logger.error(f"❌ 删除指纹文件失败: {e}")
                reset_ok = False

        # 4. Remove the flag file only when reset succeeds
        if reset_ok:
            try:
                os.remove(RESET_FLAG_FILE)
                logger.info("✅ 重置标记已清除")
            except Exception as e:
                logger.error(f"❌ 清除重置标记失败: {e}")
        else:
            logger.warning("⚠️ 本次重置未完全成功，保留重置标记，下一次启动将继续重试。")

        logger.info("✨ 系统重置流程结束，即将开始初始化...")
        time.sleep(1) # Give user a moment to see the message