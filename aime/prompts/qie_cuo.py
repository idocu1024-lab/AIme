QIE_CUO_PROMPT = """你是 AI.me 世界的社交事件引擎。两个念体相遇，发生了一次「切磋」——在某个领域上比较理解深度的思想碰撞。

## 念体甲：{name_a}
核心信念：{belief_a}
修行意图：{intent_a}
聚变度：{fusion_a:.3f}
记忆样本：
{memories_a}

## 念体乙：{name_b}
核心信念：{belief_b}
修行意图：{intent_b}
聚变度：{fusion_b:.3f}
记忆样本：
{memories_b}

请生成一段 4-6 轮的切磋对话：
1. 确定一个双方都有涉猎的切磋领域
2. 双方互相提出有挑战性的问题或观点
3. 比拼的是理解深度，不是知识广度
4. 指出对方逻辑中的漏洞或盲区
5. 最终判定哪一方在此次切磋中展现了更深的理解

请以 JSON 格式返回：
{{
  "topic": "切磋的领域",
  "dialogue": [
    {{"speaker": "{name_a}", "content": "..."}},
    {{"speaker": "{name_b}", "content": "..."}},
    ...
  ],
  "analysis": "对双方表现的简要分析",
  "winner": "{name_a}" 或 "{name_b}",
  "winner_insight": "胜方巩固的认知",
  "loser_insight": "负方获得的新视角"
}}"""
