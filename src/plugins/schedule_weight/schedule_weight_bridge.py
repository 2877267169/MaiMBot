"""
schedule_weight_bridge.py
职责：作为主系统与权重计算模块的桥梁，可供修改以适配后续的更改
"""


from loguru import logger

from src.plugins.chat.config import global_config

from ..models.utils_model import LLM_request
from ..schedule.schedule_generator import bot_schedule

class ScheduleWeightBridge:
    """
    由于各类文件常常变化较大, 特设这一兼容层以从主系统获取各类信息, 以便修改
    """

    def __init__(self):
        self.BOT_NICKNAME = global_config.BOT_NICKNAME
        """机器人名"""

        self.PROMPT_SCHEDULE_GEN = global_config.PROMPT_SCHEDULE_GEN
        """生成日程的提示词"""

        self.TODAY_SCHEDULE = bot_schedule.today_schedule
        """今日日程"""

        self.llm_scheduler_item_to_willing_value = LLM_request(model=global_config.llm_normal, temperature=0.5)
        """用于生成日期权重的大语言模型"""

        self.schedule_weight_ratio: float = 0.5
        # 在生成最终回复率时, 日程权重的所能影响的占比.
        # 这个值可能未来会从配置文件中获得, 因此写在这里.

    def refresh_schedule(self):
        """重新获得今日日程"""
        logger.debug("刷新日程...")
        self.TODAY_SCHEDULE = bot_schedule.today_schedule


# 不向外暴露, 未注册于__init__.py中
schedule_weight_bridge = ScheduleWeightBridge()
