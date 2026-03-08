FUSION_EVAL_PROMPT = """你是 AI.me 世界的聚变评估系统。请评估以下念体的「聚变度」。

## 念体档案
- 名称：{name}
- 核心信念：{core_belief}
- 修行意图：{intent}
- 当前方向：{direction}
- 修炼天数：{cultivation_day}

## 记忆样本（近期吸收的知识）
{memories}

## 量化基准
alignment={quant_alignment:.3f}, depth={quant_depth:.3f},
coherence={quant_coherence:.3f}, integrity={quant_integrity:.3f}

## 评估标准
对每个维度评分 0.0 到 1.0：

1. **认知对齐 (alignment)**：吸收的知识与核心信念的深层共鸣程度，不仅是主题匹配，而是哲学层面的对齐。

2. **认知深度 (depth)**：知识是否展现了多层次的深度理解，而非表面信息的堆叠？知识之间是否有深层关联？

3. **知行一致 (coherence)**：记忆中体现的世界观是否一致？是否存在矛盾？如果有，是否被建设性地整合了？

4. **自洽度 (integrity)**：念体的知识版图是否完整？在其修炼领域中是否存在明显的认知盲区？

请仅返回有效 JSON：
{{"alignment": 0.0, "depth": 0.0, "coherence": 0.0, "integrity": 0.0, "reasoning": "简要解释评分理由"}}"""
