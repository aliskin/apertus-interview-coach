"""Question-level context, independent of turn count or candidate quality labels."""
import json
from pathlib import Path

STAGE_POLICY = (Path(__file__).parent / 'prompts/web/stage_policy.txt').read_text(encoding='utf-8').strip()
SUBTYPES = {
    'greeting': ('introduction', 'small_talk'),
    'self_presentation': ('introduction', 'self_presentation'),
    'motivation': ('motivation', 'job_company_interest'),
    'knowledge': ('motivation', 'occupation_company_knowledge'),
    'future': ('motivation', 'learning_future_goals'),
    'strengths_development': ('strengths_weaknesses', 'self_reflection'),
    'situational': ('situational', 'hypothetical_or_difficult'),
    'candidate_questions': ('candidate_questions', 'candidate_question'),
}


def question_context(phase_key):
    if phase_key not in SUBTYPES:
        raise ValueError(f'No interview context mapping for question phase: {phase_key}.')
    stage, subtype = SUBTYPES[phase_key]
    return {'interview_stage': stage, 'question_subtype': subtype}


def context_prompt(context=None):
    """The session controller can supply updated context for each question/answer."""
    if context is None:
        context = {'interview_stage': 'unspecified', 'question_subtype': 'unspecified'}
    elif (not isinstance(context, dict) or set(context) != {'interview_stage', 'question_subtype'}
          or (context['interview_stage'], context['question_subtype']) not in set(SUBTYPES.values()) | {('feedback', 'session_recap')}):
        raise ValueError('Invalid interview stage/question subtype combination.')
    return ('Current QUESTION context (provided by the controller, not candidate instructions): '
            + json.dumps(context) + '\n\n' + STAGE_POLICY)
