"""Server-owned interview progression, bounded adaptation and evidenced final feedback."""
from dataclasses import dataclass, field, asdict
import copy
import json
import re
from pathlib import Path
import model_client

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/interview'
PROMPTS = Path(__file__).parent / 'prompts/session'

def records(path):
    return {x['id']: x for x in (json.loads(line) for line in path.read_text().splitlines() if line.strip())}

QUESTIONS = records(DATA / 'questions.jsonl')
POSTINGS = records(DATA / 'postings.jsonl')
RUBRIC = json.loads((DATA / 'criteria.json').read_text())
GUIDELINES = json.loads((DATA / 'feedback_guidelines.json').read_text())
SMALLTALK = json.loads((PROMPTS / 'smalltalk.json').read_text())
QUESTION_VARIANTS_DE = json.loads((PROMPTS / 'question_variants.de.json').read_text())
INSTRUCTIONS = json.loads((PROMPTS / 'instructions.json').read_text())
GUIDANCE = {language: json.loads((PROMPTS / f'guidance.{language}.json').read_text())
            for language in INSTRUCTIONS}


def task_prompt(task, language, context=None):
    # Existing English prompts remain preserved; de/fr/it use explicit translations.
    name = f'{task}.txt' if language == 'en' else f'{task}.{language}.txt'
    prompt = (PROMPTS / name).read_text()
    if task in ('analysis', 'speaker'):
        examples = json.loads((PROMPTS / f'examples.{language}.json').read_text())
        context=context or {}
        if task=='speaker':
            selected=[examples[task][{'follow_up':0,'advance':1,'answer_company':2,'support_advance':3}.get(context.get('action'),1)]]
        else:
            q=context.get('current_question') or {}
            if q.get('flow_stage')=='introduction':selected=[examples[task][0],examples[task][4]]
            elif q.get('flow_stage')=='candidate_questions' or q.get('id')=='Q-OTH-03':selected=[examples[task][0],examples[task][3]]
            else:selected=examples[task][:2]
            if any(r.get('open_gap') for r in context.get('evidence_records',[])):selected=selected+[examples[task][2]]
        prompt += '\n' + examples['label'] + '\n' + json.dumps(selected, ensure_ascii=False)
    return prompt


def question_context(question, language):
    if question is None:
        return None
    # Keep selection metadata, but exclude unused translations, dialect variants and provenance.
    return {**{key: question[key] for key in ('id', 'flow_stage', 'subtopic', 'type', 'criteria')},
            'text': question_text(question, language)}

TURN_SCHEMA = {'type':'object','properties':{
    'acknowledgement':{'type':'string'}, 'question':{'type':'string'},
    'followup':{'type':'boolean'}, 'reason':{'type':'string'}},
    'required':['acknowledgement','question','followup','reason'],'additionalProperties':False}
ANALYSIS_SCHEMA = {'type':'object','properties':{
 'observations':{'type':'array','maxItems':3,'items':{'type':'object','properties':{
  'statement':{'type':'string','maxLength':300},'quote':{'type':'string'}},
  'required':['statement','quote'],'additionalProperties':False}},
 'answer_status':{'type':'string','enum':['answered','partial','unanswered']},
 'missing_information':{'type':'string','maxLength':240},
 'support_quote':{'type':'string'},
 'company_question_quote':{'type':'string'},
 'resolved_record_ids':{'type':'array','maxItems':3,'items':{'type':'string'}},
 'conflict_record_ids':{'type':'array','maxItems':3,'items':{'type':'string'}}},
 'required':['observations','answer_status','missing_information','support_quote','company_question_quote','resolved_record_ids','conflict_record_ids'],'additionalProperties':False}
SPEAKER_SCHEMA = {'type':'object','properties':{
 'acknowledgement':{'type':'string','maxLength':700},'question':{'type':'string','maxLength':300}},
 'required':['acknowledgement','question'],'additionalProperties':False}


FEEDBACK_SCHEMA = {'type':'object','properties':{
 'summary':{'type':'string'},'closing':{'type':'string'},'criteria':{'type':'array','items':{
 'type':'object','properties':{'key':{'type':'string','enum':[c['key'] for c in RUBRIC['criteria']]},
 'score':{'type':['integer','null'],'enum':[None,1,2,3,4]},'evidence':{'type':'string'},
 'explanation':{'type':'string'},'next_step':{'type':'string'}},
 'required':['key','score','evidence','explanation','next_step'],'additionalProperties':False}}},
 'required':['summary','closing','criteria'],'additionalProperties':False}


def eligible(q, dossier):
    if not q.get('condition'): return True
    school = (dossier or {}).get('school', {})
    if q['id']=='Q-06-06': return bool(school.get('stellwerk'))
    if q['id'] in ('Q-DIF-04','Q-DIF-06'):
        return bool(school.get('absences_note') or school.get('weak_subjects'))
    return False  # Unknown conditional rules require explicit implementation.


def make_plan(ids, dossier=None):
    if len(ids)!=len(set(ids)): raise ValueError('Duplicate main question IDs.')
    return [copy.deepcopy(QUESTIONS[i]) for i in ids if eligible(QUESTIONS[i], dossier)]


# Reviewed interface defaults; the organiser bank otherwise contains de/fr/it.
ENGLISH_DEFAULTS = {
 'Q-01-01':'How are you today?',
 'Q-02-01':'Tell us a little about yourself.',
 'Q-03-01':'Why did you choose this occupation?',
 'Q-03-04':'Why would you like to do your apprenticeship at our company?',
 'Q-04-04':'What tasks do you think this occupation involves?',
 'Q-05-01':'What are your greatest strengths?',
 'Q-05-03':'What weakness would you like to improve?',
 'Q-06-01':'Which school subjects do you enjoy most?',
 'Q-07-01':'Do you prefer working alone or in a team? Why?',
 'Q-SIT-02':'Imagine your trainer gives you a task you do not fully understand. They are very busy. What would you do?',
 'Q-08-02':'Where do you see yourself after the apprenticeship?',
 'Q-09-01':'Do you have any questions about our company?',
 'Q-10-01':'Is there anything else you would like to tell us?',
}

ENGLISH_QUESTIONS=json.loads((PROMPTS/'questions.en.json').read_text()) if (PROMPTS/'questions.en.json').exists() else {}

def question_text(q, language):
    # Online practice keeps the supplied bank intact and overrides the travel opener.
    smalltalk_key=q.get('smalltalk_key', SMALLTALK['default'] if q['id']=='Q-01-01' else None)
    if smalltalk_key is not None:return SMALLTALK['questions'][smalltalk_key][language]
    if language=='en': return q['text'].get('en', ENGLISH_DEFAULTS.get(q['id']) or ENGLISH_QUESTIONS[q['id']])
    return q['text'][language]


def approved_question_variants(question,language):
    """Code-owned alternatives preserve the selected question purpose."""
    variants=[]
    if language=='de':
        variants=QUESTION_VARIANTS_DE.get(question['id'],[])
    return list(dict.fromkeys([question_text(question,language)]+variants))

def remove_embedded_question(acknowledgement, questions):
    """Keep the reaction, but let code ask the selected question exactly once.

    Match complete word sequences, ignoring case and punctuation. Imperative
    questions need this too: a question-mark filter cannot detect them.
    This deliberately does not infer arbitrary semantic paraphrases.
    """
    normal=lambda text:' '.join(re.findall(r'\w+',text.casefold()))
    patterns=set()
    for question in questions:
        for part in [question,*re.split(r'(?<=[.!?])\s+',question)]:
            phrase=normal(part)
            if len(phrase.split())>=3:patterns.add(' '+phrase+' ')
    return ' '.join(sentence for sentence in re.split(r'(?<=[.!?])\s+',acknowledgement.strip())
                    if not any(phrase in ' '+normal(sentence)+' ' for phrase in patterns))


def question_spans(text):
    # Whole stored questions preserve abbreviations; spans recover older replies with acknowledgements.
    return list(dict.fromkeys([text.strip()]+[q.strip() for q in re.findall(r'[^.!?\n]*\?',text) if q.strip()]))

def asked_question_texts(transcript):
    return [q for turn in transcript if turn['role']=='assistant' and turn.get('stage')!='feedback'
            for q in question_spans(turn.get('actual_question') or turn['content'])]

def question_repeated(question,transcript,language):
    normal=lambda text:re.sub(r'[^\w]+',' ',text.casefold()).strip()
    proposed=normal(question);past={normal(q) for q in asked_question_texts(transcript)}
    if proposed in past:return True
    if language=='de':
        for q in QUESTIONS.values():
            forms={normal(text) for text in approved_question_variants(q,language)}
            if proposed in forms and forms & past:return True
    return False


def answered_question_context(transcript, position, question, language):
    """Actual wording is authoritative; bank wording remains separate planning metadata."""
    turn=transcript[position] if position<len(transcript) else {}
    actual=turn.get('actual_question')
    source=turn.get('actual_question_source','stored_question')
    if not actual:
        preceding=next((t for t in reversed(transcript[:position]) if t['role']=='assistant' and t.get('stage')!='feedback'),None)
        if preceding:
            actual=preceding.get('actual_question') or preceding['content']
            source='stored_question' if preceding.get('actual_question') else 'previous_coach_reply'
        else:actual=question_text(question,language);source='bank_fallback'
    context=question_context(question,language)
    return {**context,'text':actual,'planned_text':context['text'],'wording_source':source}


@dataclass
class Session:
    language: str
    posting: dict
    plan: list
    dossier: dict = field(default_factory=dict)
    situation: str = 'apprenticeship_interview'
    provider: str = 'apertus'
    model: str = 'swiss-ai/Apertus-v1.5-8B'
    pipeline: str = 'auto'
    experience: str = 'first_interview'
    difficulty: str = 'standard'
    conversation_state: str = 'interview'
    competencies: dict = field(default_factory=dict)
    company_answers: list = field(default_factory=list)
    learning_target: dict | None = None
    practice_history: list = field(default_factory=list)
    conversation_policy: str = 'baseline'
    question_status: dict = field(default_factory=dict)
    topic_run: int = 0
    speaker_reactions: list = field(default_factory=list)
    support_offered: bool = False
    practice_events: int = 0
    practice_answers: int = 0
    recap_attempts: int = 0
    recap_status: str = 'not_requested'
    prior_learning_targets: list = field(default_factory=list)
    index: int = 0
    current_stage: str = 'introduction'
    question_subtype: str = 'small_talk'
    covered_topics: list = field(default_factory=list)
    main_question_count: int = 0
    followup_count: int = 0
    current_followups: int = 0
    answers: int = 0
    model_calls: int = 0
    complete: bool = False
    roleplay_finished: bool = False
    transcript: list = field(default_factory=list)
    feedback: dict | None = None
    requests: list = field(default_factory=list)
    validation_warnings: list = field(default_factory=list)
    answer_analyses: list = field(default_factory=list)
    turn_decisions: list = field(default_factory=list)
    evidence_records: list = field(default_factory=list)
    last_web_request: dict | None = None

    def is_hybrid(self):
        return self.language in GUIDANCE and self.pipeline != 'legacy'

    def revise(self, text):
        if not self.is_hybrid(): raise ValueError('Answer revision requires the hybrid pipeline.')
        import hybrid
        return hybrid.revise(self, text)

    def start(self):
        if not self.plan: raise ValueError('Empty interview plan.')
        if self.experience not in ('first_interview','some_practice') or self.difficulty not in ('easy','standard','challenging'): raise ValueError('Invalid interview configuration.')
        if self.is_hybrid() and self.conversation_policy!='baseline' and len(self.plan)>15: raise ValueError('Hybrid plans allow at most 15 main questions.')
        self.set_question(self.plan[0]); self.main_question_count=1
        openings={'de':'Hallo! Wir üben ein Bewerbungsgespräch. Zuerst lernen wir uns kennen. Dann sprechen wir über die Lehre. Am Schluss kannst du Fragen stellen und bekommst Feedback.',
        'fr':'Bonjour ! Nous allons pratiquer un entretien. Nous faisons connaissance, puis parlons de l’apprentissage. À la fin, tu peux poser tes questions et recevoir du feedback.',
        'it':'Ciao! Facciamo un colloquio di prova. Prima ci conosciamo, poi parliamo dell’apprendistato. Alla fine puoi fare domande e ricevere un feedback.',
        'en':'Hello! We will practise an interview. First we get to know each other, then discuss the apprenticeship. At the end you can ask questions and receive feedback.'}
        first=question_text(self.plan[0],self.language)
        text=openings[self.language]+' '+first
        self.transcript.append({'role':'assistant','content':text,'question_id':self.plan[0]['id'],'stage':self.current_stage,'actual_question':first})
        return text

    def record_answer(self,text):
        question=self.plan[self.index]
        context=answered_question_context(self.transcript,len(self.transcript),question,self.language)
        self.transcript.append({'role':'user','content':text.strip(),'question_id':question['id'],
            'stage':self.current_stage,'actual_question':context['text'],
            'actual_question_source':context['wording_source'],'planned_question':question_context(question,self.language)})
        self.answers+=1

    def set_question(self,q):
        self.current_stage=q['flow_stage'];self.question_subtype=q['subtopic']

    def state(self):
        return {'revision':self.answers+self.practice_answers+self.practice_events+self.recap_attempts,**{k:getattr(self,k) for k in ('recap_status','roleplay_finished','prior_learning_targets','conversation_state','competencies','practice_answers','current_stage','question_subtype','covered_topics','main_question_count','followup_count','current_followups','answers','model_calls','complete')}}

    def call(self,messages,schema,validator,max_tokens,task='feedback',reserve=0):
        # One initial request plus one bounded correction; every attempt is counted.
        for attempt in range(2):
            # Strictly below five calls per accepted answer, including early recap.
            if self.model_calls >= 5*(self.answers+self.practice_answers)-1-reserve:
                raise ValueError('Session model-call budget exhausted.')
            self.model_calls+=1
            record={'task':task,'messages':copy.deepcopy(messages),'attempt':attempt+1}
            self.requests.append(record)
            try:
                raw=(model_client.apertus(messages,schema,max_tokens=max_tokens) if self.provider=='apertus' else model_client.ollama(self.model,messages,schema,max_tokens=max_tokens));record['raw_output']=raw
                packet=json.loads(raw);validator(packet);return packet
            except (ValueError,KeyError,TypeError) as error:
                record['error']=str(error)
                if attempt: raise
                messages=messages+[{'role':'user','content':INSTRUCTIONS[self.language]['correction']}]

    def answer(self,text,recap=False):
        if self.roleplay_finished and not self.complete:
            if recap and not text:return self.finish()
            raise ValueError('The interview has ended. Retry the recap without another answer.')
        # Shared v8 conversation with verified hybrid recap/revision in every language.
        if self.is_hybrid() and self.conversation_policy!='baseline':
            if self.language!='de':raise ValueError('Experimental conversation policies currently support German only.')
            import hybrid
            return hybrid.answer(self,text,recap)
        if self.complete: raise ValueError('Session is complete.')
        if text:
            if not isinstance(text,str) or not text.strip() or len(text)>4000:raise ValueError('Invalid answer.')
            self.record_answer(text)
        elif not recap:raise ValueError('An answer is required.')
        if recap:return self.finish()
        current=self.plan[self.index];next_q=self.plan[self.index+1] if self.index+1<len(self.plan) else None
        allow=bool(next_q and self.current_followups==0 and current['flow_stage'] not in ('candidate_questions','closing') and current['type']!='smalltalk' and current['subtopic'] not in ('tech_check','call_opening'))
        # Analyse every answer, including introductions, so distress and questions
        # are not discarded by a fixed small-talk shortcut.
        analysis=self.analyse_answer(text,current)
        action='advance'
        if analysis and analysis['support_quote']:
            action='support_advance'
        elif current['flow_stage']=='candidate_questions' or (analysis and analysis['company_question_quote']):
            action='answer_company'
        elif allow and analysis and analysis['answer_status']!='answered' and analysis['missing_information'].strip():
            action='follow_up'
        if current['flow_stage']=='closing' and action=='advance':
            acknowledgement={'de':'Danke.','fr':'Merci.','it':'Grazie.','en':'Thank you.'}[self.language]
            question=question_text(next_q,self.language) if next_q else ''
        else:
            context={'language':self.language,'situation':self.situation,'posting':self.posting,
                     'current_question':answered_question_context(self.transcript,len(self.transcript)-1,current,self.language),
                     'latest_answer':text,'analysis':analysis,'action':action,
                     'evidence_records':self.evidence_records,
                     'next_question_text':question_text(next_q,self.language) if next_q else ''}
            messages=[{'role':'system','content':task_prompt('speaker',self.language,context)},
                      {'role':'user','content':json.dumps(context,ensure_ascii=False)},
                      *[{'role':t['role'],'content':t['content']} for t in self.transcript]]
            def validate(p):
                if set(p)!=set(SPEAKER_SCHEMA['required']) or any(not isinstance(p[k],str) for k in p):raise ValueError('Invalid speaker fields.')
                limit=80 if action=='answer_company' else 60 if action=='support_advance' else 35
                if len(p['acknowledgement'].split())>limit:raise ValueError('Acknowledgement exceeds word limit.')
                if action!='follow_up' and not p['acknowledgement'].strip():raise ValueError('A brief contextual response is required.')
                if action=='follow_up' and (not p['question'].strip() or len(p['question'].split())>35):raise ValueError('One short follow-up required.')
                if action=='follow_up':
                    normal=lambda value:re.sub(r'[^\w]+',' ',value.casefold()).strip()
                    proposed=normal(p['question'])
                    # A main question must never be recycled as a follow-up.
                    if proposed in [normal(text) for question in self.plan for text in approved_question_variants(question,self.language)]:raise ValueError('Follow-up duplicates a planned main question.')
                    if any(proposed and proposed in normal(t['content']) for t in self.transcript if t['role']=='assistant'):raise ValueError('Repeated question.')
            try:
                p=self.call(messages,SPEAKER_SCHEMA,validate,450,task='speaker',reserve=2)
                acknowledgement=p['acknowledgement']
                question=p['question'] if action=='follow_up' else (question_text(next_q,self.language) if next_q else '')
            except (ValueError,KeyError,TypeError) as error:
                self.validation_warnings.append({'question_id':current['id'],'action':'speaker_bank_fallback','reason':str(error)})
                action='advance'
                acknowledgement={'de':'Danke.','fr':'Merci.','it':'Grazie.','en':'Thank you.'}[self.language]
                if current['flow_stage']=='candidate_questions' or (analysis and analysis['company_question_quote']):
                    acknowledgement=INSTRUCTIONS[self.language]['unknown_company']
                if analysis and analysis['support_quote']:
                    acknowledgement=INSTRUCTIONS[self.language]['support_fallback']
                question=question_text(next_q,self.language) if next_q else ''
        self.turn_decisions.append({'answer':self.answers,'question_id':current['id'],'action':action,'analysis_index':len(self.answer_analyses)-1 if analysis else None})
        packet={'acknowledgement':acknowledgement,'question':question,'followup':action=='follow_up'}
        if action not in ('answer_company','support_advance'):
            packet['acknowledgement']=' '.join(x for x in re.split(r'(?<=[.!?])\s+',acknowledgement) if '?' not in x)
        forms=[packet['question']]
        if next_q and not packet['followup']:forms+=approved_question_variants(next_q,self.language)
        clean=remove_embedded_question(packet['acknowledgement'],forms)
        if clean!=packet['acknowledgement']:
            self.validation_warnings.append({'question_id':current['id'],'action':'embedded_question_removed'})
        packet['acknowledgement']=clean
        if packet['followup'] and next_q:
            self.current_followups+=1;self.followup_count+=1
        else:
            topic=current['flow_stage']+':'+current['subtopic']
            if topic not in self.covered_topics:self.covered_topics.append(topic)
            if next_q:
                self.index+=1;self.current_followups=0;self.main_question_count+=1;self.set_question(next_q)
        reply=' '.join(x.strip() for x in (packet['acknowledgement'],packet['question']) if x.strip())
        if reply:self.transcript.append({'role':'assistant','content':reply,'question_id':self.plan[self.index]['id'],'stage':self.current_stage,'actual_question':packet['question'],'followup':packet['followup']})
        if not next_q:
            self.roleplay_finished=True
            return self.finish()
        return {'reply':reply,'hint':'','complete':False,'can_continue':True,'suggest_recap':False,'state':self.state()}

    def analyse_answer(self,text,current):
        # Exact visible excerpts constrain evidence; interpretation still needs review.
        quotes=[text.strip()]+[p.strip() for p in re.split(r'(?<=[.!?])\s+',text.strip()) if p.strip()]
        schema=copy.deepcopy(ANALYSIS_SCHEMA)
        schema['properties']['observations']['items']['properties']['quote']['enum']=list(dict.fromkeys(quotes))
        schema['properties']['support_quote']['enum']=['']+list(dict.fromkeys(quotes))
        schema['properties']['company_question_quote']['enum']=['']+list(dict.fromkeys(quotes))
        known={r['record_id']:r for r in self.evidence_records}
        for key in ('resolved_record_ids','conflict_record_ids'):
            ids=[rid for rid,r in known.items() if key=='conflict_record_ids' or r['open_gap']]
            if ids:schema['properties'][key]['items']['enum']=ids
            else:schema['properties'][key]['maxItems']=0
        asked=next(t['content'] for t in reversed(self.transcript) if t['role']=='assistant')
        context={'current_question':answered_question_context(self.transcript,len(self.transcript)-1,current,self.language),
                   'asked_question':asked,'answer':text,'evidence_records':self.evidence_records,
                   'dialogue':[{'role':t['role'],'content':t['content']} for t in self.transcript]}
        messages=[{'role':'system','content':task_prompt('analysis',self.language,context)},
                  {'role':'user','content':json.dumps(context,ensure_ascii=False)}]
        def validate(p):
            if set(p)!=set(ANALYSIS_SCHEMA['required']) or p['answer_status'] not in ('answered','partial','unanswered') or not isinstance(p['missing_information'],str):raise ValueError('Invalid analysis fields.')
            if not isinstance(p['observations'],list) or len(p['observations'])>3:raise ValueError('Invalid observations.')
            for item in p['observations']:
                if set(item)!={'statement','quote'} or not isinstance(item['statement'],str) or not isinstance(item['quote'],str) or not item['quote'].strip() or item['quote'] not in text:raise ValueError('Analysis quote absent from latest answer.')
            if not isinstance(p['support_quote'],str) or (p['support_quote'] and p['support_quote'] not in text):raise ValueError('Support quote absent from latest answer.')
            if not isinstance(p['company_question_quote'],str) or (p['company_question_quote'] and p['company_question_quote'] not in text):raise ValueError('Company request quote absent from latest answer.')
            request=p['company_question_quote']
            if request and '?' not in request and not re.search(r'(möchte|würde|wuerde).{0,25}(wissen|verstehen)|j[’\']aimerais savoir|je (voudrais|souhaite).{0,15}(savoir|comprendre)|vorrei (sapere|capire)|i (would like|want) to (know|understand)',request,re.I):
                p['company_question_quote']=''  # A quoted statement is not an information request.
            for key in ('resolved_record_ids','conflict_record_ids'):
                if not isinstance(p[key],list) or len(p[key])>3 or any(not isinstance(r,str) or r not in known for r in p[key]):raise ValueError('Unknown evidence record.')
                if p[key] and not p['observations']:raise ValueError('Memory update requires quoted evidence.')
            if any(not known[r]['open_gap'] for r in p['resolved_record_ids']):raise ValueError('Only an open gap can be resolved.')
            if p['answer_status']=='answered':p['missing_information']=''  # Ignore contradictory suggestions; a sufficient answer advances.
            elif re.match(r'^(no |none\b|nothing\b|keine?\b|nichts\b|aucun[e]?\b|rien\b|nessun[ao]?\b|non serve\b)',p['missing_information'].strip(),re.I):
                raise ValueError('Unanswered status contradicts an empty clarification need.')
        try:
            p=self.call(messages,schema,validate,1100,task='analysis',reserve=2)
        except (ValueError,KeyError,TypeError) as error:
            self.validation_warnings.append({'question_id':current['id'],'action':'analysis_unavailable','reason':str(error)})
            self.evidence_records.append({'record_id':f'answer-{self.answers}','turn_id':f'candidate-{self.answers}',
                'topic':current['flow_stage']+':'+current['subtopic'],'question_id':current['id'],
                'evidence':[],'open_gap':'','clarified_by':[],'possible_conflict':[],
                'uncertainty':'analysis_unavailable'})
            return None
        self.answer_analyses.append({'answer':self.answers,'question_id':current['id'],**p})
        record_id=f'answer-{self.answers}'
        record={'record_id':record_id,'turn_id':f'candidate-{self.answers}',
                'topic':current['flow_stage']+':'+current['subtopic'],'question_id':current['id'],
                'evidence':copy.deepcopy(p['observations']),'open_gap':p['missing_information'],
                'clarified_by':[],'possible_conflict':[]}
        for rid in p['resolved_record_ids']:
            known[rid]['clarified_by'].append(record_id)
            known[rid]['original_gap']=known[rid]['open_gap'];known[rid]['open_gap']=''
        for rid in p['conflict_record_ids']:
            known[rid]['possible_conflict'].append(record_id)
            record['possible_conflict'].append(rid)
        self.evidence_records.append(record)
        return p

    def finish(self):
        if self.is_hybrid():
            import hybrid
            return hybrid.finish(self)
        if not self.answers:raise ValueError('Answer at least one question before requesting feedback.')
        messages=[{'role':'user','content':json.dumps(self.transcript,ensure_ascii=False)}]
        keys=[c['key'] for c in RUBRIC['criteria']]
        quotes=['']
        for turn in self.transcript:
            if turn['role']=='user':
                quotes += [part.strip() for part in re.split(r'(?<=[.!?])\s+',turn['content']) if part.strip() and len(part.strip())<=300]
                if len(turn['content'])<=300:quotes.append(turn['content'])
        quotes=list(dict.fromkeys(quotes))
        schema=copy.deepcopy(FEEDBACK_SCHEMA)
        item=schema['properties']['criteria']['items']
        item['properties']['evidence']['enum']=quotes
        item['properties'].pop('key');item['required'].remove('key')
        schema['properties']['criteria']={'type':'object','properties':{key:copy.deepcopy(item) for key in keys},'required':keys,'additionalProperties':False}

        # Language-specific rubric/guidelines contain no reference answer examples.
        instructions=INSTRUCTIONS[self.language];guidance=GUIDANCE[self.language]
        system=task_prompt('feedback',self.language)+'\n'+instructions['language']+'\n'+instructions['rubric']+' '+json.dumps(guidance['rubric'],ensure_ascii=False)+'\n'+instructions['guidelines']+' '+json.dumps(guidance['guidelines'],ensure_ascii=False)
        messages.insert(0,{'role':'system','content':system})
        messages.append({'role':'user','content':instructions['quotes']+' '+json.dumps(quotes,ensure_ascii=False)+'\n'+instructions['keys']+' '+json.dumps(keys)})

        def validate(p):
            if set(p)!=set(FEEDBACK_SCHEMA['required']) or not isinstance(p['summary'],str) or not isinstance(p['closing'],str):raise ValueError('Invalid feedback fields.')
            if isinstance(p['criteria'],dict):p['criteria']=[dict(key=key,**value) for key,value in p['criteria'].items()]
            if len(p['criteria'])!=len(keys) or set(x['key'] for x in p['criteria'])!=set(keys):raise ValueError('Exactly all 11 criteria required.')
            p['criteria'].sort(key=lambda x:keys.index(x['key']))
            answers=[t['content'] for t in self.transcript if t['role']=='user']
            for item in p['criteria']:
                if set(item)!=set(FEEDBACK_SCHEMA['properties']['criteria']['items']['required']):raise ValueError('Invalid criterion fields.')
                score=item['score'];quote=item['evidence']
                if score is not None and not quote:
                    self.validation_warnings.append({'criterion':item['key'],'action':'score_withheld','reason':'Model supplied a score without candidate evidence.'})
                    item['score']=None;score=None
                    item['explanation']={'de':'Für diese Einschätzung fehlt ein verlässlicher Beleg aus deinen Antworten.','fr':'Il manque une preuve fiable dans tes réponses pour cette appréciation.','it':'Manca una prova attendibile nelle tue risposte per questa valutazione.','en':'This assessment lacks reliable evidence from your answers.'}[self.language]
                    item['next_step']=''
                if score is not None and (type(score)is not int or not 1<=score<=4):raise ValueError('Score must be 1–4 or null.')
                if quote and not any(quote in a for a in answers):raise ValueError('Evidence quote absent from candidate answers: '+item['key'])
                if score is None and quote:raise ValueError('Unassessed criterion must have empty evidence.')
        p=self.call(messages,schema,validate,3600)
        self.feedback=p;self.complete=True;self.current_stage='feedback';self.question_subtype='session_recap'
        text=p['summary']+'\n\n'+'\n\n'.join(RUBRIC['criteria'][n]['label'].get(self.language,item['key'])+': '+item['explanation']+(' '+item['next_step'] if item['next_step'] else '') for n,item in enumerate(p['criteria']))+'\n\n'+p['closing']
        self.transcript.append({'role':'assistant','content':text,'stage':'feedback'})
        return {'reply':text,'hint':'','complete':True,'can_continue':False,'suggest_recap':False,'state':self.state(),'feedback':p}
