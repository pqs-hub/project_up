# generate_dataset.py

import logging
import sys
from pathlib import Path

# 保证项目根目录在 path 中，便于导入同目录模块
sys.path.insert(0, str(Path(__file__).resolve().parent))

from AdversarialDatasetGenerator import AdversarialDatasetGenerator

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/generation.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


def main():
    # 创建生成器
    generator = AdversarialDatasetGenerator(config_path='config.yaml')
    
    # 生成数据集
    try:
        generator.generate()
    except KeyboardInterrupt:
        logger.info("用户中断")
    except Exception as e:
        logger.error(f"生成失败: {e}", exc_info=True)


if __name__ == "__main__":
    main()
