"""
schedule_response_weight_manager.py
"""

import datetime
import re
from typing import Dict, Union, List
from loguru import logger

# 用于导入各类需要的数据参数
from .schedule_weight_bridge import schedule_weight_bridge

#  ------------------ 一些小工具和算法 ------------------
def is_valid_time(time_str: str) -> bool:
    """
    检查时间字符串是否符合 "HH:MM" 格式（00:00 到 23:59）。
    参数：
        time_str (str): 需要检查的时间字符串。
    返回：
        bool: 如果符合格式返回 True，否则返回 False。
    """
    # 正则表达式模式：
    # ^([01]\d|2[0-3]):[0-5]\d$
    # 1. ^ 和 $ 确保整个字符串严格匹配
    # 2. 小时部分：
    #    - [01]\d：00-19 或 0-9（但需两位数字）
    #    - 2[0-3]：20-23
    # 3. 分钟部分：
    #    - [0-5]\d：00-59
    pattern = r'^([01]\d|2[0-3]):[0-5]\d$'
    return bool(re.match(pattern, time_str))


def time_str_to_seconds(time_str: str) -> int:
    """
    将符合 "HH:MM" 格式的时间字符串转换为当天的总秒数。
    参数：
        time_str (str): 需要转换的时间字符串（如 "07:01"）。
    返回：
        int: 如果时间有效则返回总秒数，否则返回抛出异常。
    """
    if not is_valid_time(time_str):
        raise ValueError(time_str + "不符合 小时:分钟 的时间格式")

    hours_str, minutes_str = time_str.split(':')
    hours = int(hours_str)
    minutes = int(minutes_str)

    return hours * 3600 + minutes * 60


def adjust_time_list_to_center(time_list: List[int]) -> List[int]:
    """生成一个新时间表列表, 但是键内的时间, 都在日程表时间段的中央"""
    time_list = time_list.copy()

    # 将昨日最后一项和明日第一项也加入时间表, 昨日为负值, 明日为大于24点所对应秒数的值
    # 由于昨日真实的时间表可能不存在, 明日的可能还未生成, 姑且在计算时认为昨天和明天都是今天日程表的重复()
    first_item_time = time_list[0]

    # 明日第一项: 高于 60*60*24的大值
    first_item_time += 60 * 60 * 24

    time_list.append(first_item_time)

    new_time_list = []
    for i, sec in enumerate(time_list[0:-1]):
        # 获取日程持续时间
        d = time_list[i + 1] - time_list[i]

        # 居中
        sec += int(d / 2)

        new_time_list.append(sec)

    return new_time_list


def normalize_list(input_list: Union[List[int], List[float]]) -> List[float]:
    """
    将字典的值归一化到 [0, 1] 范围。
    若字典为空或所有值相同，返回空字典或统一设为 0.5。
    限定为全int列表和全float列表
    """
    if len(input_list) == 0:
        return []

    max_val = max(input_list)
    min_val = min(input_list)

    # 处理所有值相同的情况
    if max_val == min_val:
        return [0.5] * len(input_list)  # 全为0.5 的列表

    # 线性归一化公式
    return [(v - min_val) / (max_val - min_val) for v in input_list]


# ------------------ 小工具和算法结束 ------------------

class ScheduleResponseWeightManager:
    """
    根据日程生成各日程项权重的管理类
    """

    def __init__(self):
        self.enable: bool = True  # 本模块是否启用
        self.today_schedule_response_weight: Dict[int, float] = {}  # 存储今日的权重, 但是键是秒
        self.centralized_time_schedule_weight: Dict[int, float] = {}  # 存储今日的权重, 但是键(秒数)调整到了日程项的中央
        self.schedule_weight_ratio = schedule_weight_bridge.schedule_weight_ratio
        # 从兼容层获取日程权重的所能影响的占比
        self.weight_max: float = 1.0
        self.weight_min: float = 0.0

    async def generate_weight(self) -> None:
        if self.enable:
            """根据每个日程项的描述生成一个回复意愿基础值"""
            # 0 检查日程项是否为空
            if len(schedule_weight_bridge.TODAY_SCHEDULE) == 0:
                logger.error("日程项为空! 请检查日程")
                self.enable = False  # 出现错误, 重启前, 保持关闭
                return  #
            try:
                prompt_myself = \
                    f"你是{schedule_weight_bridge.BOT_NICKNAME}，{schedule_weight_bridge.PROMPT_SCHEDULE_GEN},"
                prompt_text = ("现在, 你有多大的意愿值现在刷群并回复群友? "
                               "仅输出以一个0~1之间的小数给出你的意愿值, 不需要任何其他文本")

                for time_str, schedule_item in schedule_weight_bridge.TODAY_SCHEDULE.items():
                    # 1 检查日期格式
                    if is_valid_time(time_str) is False:
                        logger.error("日程的时间存在问题." + time_str)
                        raise ValueError(time_str + "不符合 小时:分钟 的时间格式")

                    # 将时间字符串转化为今天的秒数(例如到07:01分过了25260秒)
                    time_sec: int = time_str_to_seconds(time_str)

                    prompt_date = f'你今日日程:\n{schedule_weight_bridge.TODAY_SCHEDULE}\n你现在正在{schedule_item}\n'

                    # 2 构造提示词并生成权重
                    # generate_response 返回 (content, reasoning_content)
                    logger.debug(f"正在为 {time_str} 的 {schedule_item} 日程生成权重...")
                    llm_willing_str, _ = await (
                        schedule_weight_bridge.llm_scheduler_item_to_willing_value.generate_response(
                            prompt_myself + prompt_date + prompt_text))  # 生成此日程项的回复意愿

                    # 3 从字符串中获取权重
                    pattern = r'[-+]?(?:\d+\.\d+|\.\d+|\d+)'  # 获取文本中出现的第一个小数或整数的正则表达式
                    match = re.search(pattern, llm_willing_str)
                    willing_value: float = float(match.group() if match else 0.0)  # 在此日程中,机器的意愿值

                    # 权重文件的字典索引是整形的今日秒数
                    self.today_schedule_response_weight[time_sec] = willing_value  # 添加键值对

                    logger.debug(f"时间: {time_str}: 权重: {willing_value}; 日程项:{schedule_item}")

                # 4 生成完毕后的调整
                # 将字典内所有意愿值值归一化(限制在0~1内)
                self._normalize_weight()
                # 将日程权重调整到 min 和 max 规定的范围内
                self._adjust_weight()
                # 排列时间, 让键内的时间处于日程时间段的中央
                self._centralize_schedule_time()

                logger.success("日期权重生成成功")

            except Exception as e:
                self.today_schedule_response_weight = {}  # 中途失败, 意愿列表重置为空
                logger.error(f"根据日程项生成回复意愿值失败,此功能关闭.(重启程序以重新尝试): {str(e)}")
                self.enable = False  # 出现错误, 重启前, 保持关闭
        else:
            logger.debug("日程权重已禁用, 但还在被调用")

        return

    async def refresh(self) -> None:
        """
        刷新今日权重
        """
        logger.info("正在刷新日程权重")
        # 重新获取日程
        schedule_weight_bridge.refresh_schedule()

        # 根据新日程重新生成
        await self.generate_weight()
        return

    def _normalize_weight(self) -> None:
        """
        将权重字典的值归一化到 [0, 1] 范围。
        所有值相同，统一设为 0.5。
        """
        if len(self.today_schedule_response_weight) == 0:
            return

        key_list = self.today_schedule_response_weight.keys()

        # 归一化权重
        weight_list: list[float] = normalize_list(list(self.today_schedule_response_weight.values()))

        self.today_schedule_response_weight = dict(zip(key_list, weight_list))
        return

    def _adjust_weight(self) -> None:
        """
        将日程权重调整到 min 和 max 规定的范围内
        """

        # 如果需要调整范围, 将日程权重调整到 weight_min 和 weight_max 规定的范围内
        if self.weight_min != 0.0 or self.weight_max != 1.0:
            range_value: float = self.weight_max - self.weight_min
            min_value: float = self.weight_min
            self.today_schedule_response_weight = {k: (v * range_value) + min_value for k, v in
                                                   self.today_schedule_response_weight.items()}
        return

    def _centralize_schedule_time(self):
        """将日程表字典的键从各日程开始时间改到日程中央, 用于获取任意时间权值"""
        # 各日程开始时间列表(秒)
        time_list: list[int] = list(self.today_schedule_response_weight.keys())

        # 各日程权重
        weight_list: list[float] = list(self.today_schedule_response_weight.values())

        # 居中, 将字典的键从各日程开始时间改到日程中央
        time_list = adjust_time_list_to_center(time_list)

        # 合并 键列表 和 值列表 为字典
        self.centralized_time_schedule_weight = dict(zip(time_list, weight_list))

    def seconds_since_midnight(self):
        """获取今日从零时起到现在的秒数"""
        now = datetime.datetime.now()
        today_zero = now.replace(hour=0, minute=0, second=0, microsecond=0)
        delta = now - today_zero
        return int(delta.total_seconds())

    def get_now_weight(self, now_time_sec: int) -> float:
        """
        设计思路:
        假想将 "时间-日程权重" 这一键值对, 绘制成一张折线图, 而此函数, 就是在折线图的折线上取点.(插值法)
        """

        centralized_time_list = list(self.centralized_time_schedule_weight.keys())
        weight_list = list(self.centralized_time_schedule_weight.values())

        if now_time_sec < centralized_time_list[0]:
            now_time_sec += 24 * 60 * 60

        for i in range(len(centralized_time_list) - 1):
            # 简化的链式比较
            if centralized_time_list[i] <= now_time_sec < centralized_time_list[i + 1]:
                # 获取当前时间在日程时间段内的占比
                weight_percent = normalize_list(
                    [now_time_sec, centralized_time_list[i], centralized_time_list[i + 1]]
                )[0]

                return weight_percent * weight_list[i]
        logger.error("获取日期权重错误")
        self.enable = False
        raise ValueError(f"获取日期权重错误: \n"
                         f" now_time_sec:{now_time_sec};\n"
                         f"centralized_time_list{centralized_time_list};\n")

    def get_schedule_weight_ratio(self) -> float:
        """在生成最终回复率时, 日程权重的所能影响的占比."""
        return self.schedule_weight_ratio

    def is_enable(self) -> bool:
        return self.enable


# schedule_response_weight_manager 向外暴露
schedule_response_weight_manager = ScheduleResponseWeightManager()


