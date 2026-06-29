"""教育多智能体评估系统 - 量规数据包

量规版本说明：
- scoring_rubric_v4.json : 形成性评价量规 v4（四维度 × 13 二级指标，1-5 分制）
- collab_rubric.json    : 协作能力量规（自评准确性 + 互评客观性，0-100 分制）

使用方式：
    from rubrics.load_rubric import get_scoring_rubric, get_collab_rubric
    
    rubric = get_scoring_rubric()           # 完整量规
    theory = rubric.get_dimension("theory") # 理论维度
"""
