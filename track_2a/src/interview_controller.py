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
INSTRUCTIONS = json.loads((PROMPTS / 'instructions.json').read_text())
GUIDANCE = {language: json.loads((PROMPTS / f'guidance.{language}.json').read_text())
            for language in INSTRUCTIONS}


def task_prompt(task, language):
    # Existing English prompts remain preserved; de/fr/it use explicit translations.
    name = f'{task}.txt' if language == 'en' else f'{task}.{language}.txt'
    return (PROMPTS / name).read_text()


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
 'Q-01-01':'Did you find your way here easily?',
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

def question_text(q, language):
    if language=='en': return q['text'].get('en', ENGLISH_DEFAULTS.get(q['id'],q['text']['de']))
    return q['text'][language]


@dataclass
class Session:
    language: str
    posting: dict
    plan: list
    dossier: dict = field(default_factory=dict)
    situation: str = 'apprenticeship_interview'
    provider: str = 'apertus'
    model: str = 'swiss-ai/Apertus-v1.5-8B'
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

    def start(self):
        if not self.plan: raise ValueError('Empty interview plan.')
        self.set_question(self.plan[0]); self.main_question_count=1
        openings={'de':'Hallo! Wir üben ein Bewerbungsgespräch. Zuerst lernen wir uns kennen. Dann sprechen wir über die Lehre. Am Schluss kannst du Fragen stellen und bekommst Feedback.',
        'fr':'Bonjour ! Nous allons pratiquer un entretien. Nous faisons connaissance, puis parlons de l’apprentissage. À la fin, tu peux poser tes questions et recevoir du feedback.',
        'it':'Ciao! Facciamo un colloquio di prova. Prima ci conosciamo, poi parliamo dell’apprendistato. Alla fine puoi fare domande e ricevere un feedback.',
        'en':'Hello! We will practise an interview. First we get to know each other, then discuss the apprenticeship. At the end you can ask questions and receive feedback.'}
        first=question_text(self.plan[0],self.language)
        if self.language=='en' and self.plan[0]['id']=='Q-01-01':first='Did you find your way here easily?'
        text=openings[self.language]+' '+first
        self.transcript.append({'role':'assistant','content':text,'question_id':self.plan[0]['id'],'stage':self.current_stage})
        return text

    def set_question(self,q):
        self.current_stage=q['flow_stage'];self.question_subtype=q['subtopic']

    def state(self):
        return {k:getattr(self,k) for k in ('current_stage','question_subtype','covered_topics','main_question_count','followup_count','current_followups','answers','model_calls','complete')}

    def call(self,messages,schema,validator,max_tokens):
        # One initial request plus one bounded correction; every attempt is counted.
        for attempt in range(2):
            self.model_calls+=1
            record={'messages':copy.deepcopy(messages),'attempt':attempt+1}
            self.requests.append(record)
            try:
                raw=(model_client.apertus(messages,schema,max_tokens=max_tokens) if self.provider=='apertus' else model_client.ollama(self.model,messages,schema,max_tokens=max_tokens));record['raw_output']=raw
                packet=json.loads(raw);validator(packet);return packet
            except (ValueError,KeyError,TypeError) as error:
                record['error']=str(error)
                if attempt: raise
                messages=messages+[{'role':'user','content':INSTRUCTIONS[self.language]['correction']}]

    def answer(self,text,recap=False):
        if self.complete: raise ValueError('Session is complete.')
        if text:
            if not isinstance(text,str) or not text.strip() or len(text)>4000:raise ValueError('Invalid answer.')
            self.transcript.append({'role':'user','content':text.strip(),'question_id':self.plan[self.index]['id'],'stage':self.current_stage});self.answers+=1
        elif not recap:raise ValueError('An answer is required.')
        if recap:return self.finish()
        current=self.plan[self.index];next_q=self.plan[self.index+1] if self.index+1<len(self.plan) else None
        allow=self.current_followups==0 and current['flow_stage'] not in ('candidate_questions','closing') and current['type']!='smalltalk' and current['subtopic'] not in ('tech_check','call_opening')
        context={'language':self.language,'situation':self.situation,'posting':self.posting,'current_question':question_context(current,self.language),
        'next_question':question_context(next_q,self.language),'next_question_text':question_text(next_q,self.language) if next_q else '',
        'allow_followup':bool(allow and next_q),'state':self.state()}
        messages=[{'role':'system','content':task_prompt('interviewer',self.language)+'\n'+INSTRUCTIONS[self.language]['context']+' '+json.dumps(context,ensure_ascii=False)},
        *[{'role':t['role'],'content':t['content']} for t in self.transcript]]
        def validate(p):
            if set(p)!=set(TURN_SCHEMA['required']) or type(p['followup']) is not bool or any(not isinstance(p[k],str) for k in ('acknowledgement','question','reason')):raise ValueError('Invalid interviewer fields.')
            if next_q and p['followup'] and not p['question'].strip():raise ValueError('A follow-up question is required.')
            if p['followup'] and not allow:raise ValueError('Follow-up forbidden at this point.')
            if not next_q and (p['question'] or p['followup']):raise ValueError('End role-play without another question.')
        messages.append({'role':'user','content':INSTRUCTIONS[self.language]['task']+' '+json.dumps({'next_question_text':context['next_question_text'],'allow_followup':context['allow_followup'],'current_question':current['text'][self.language if self.language!='en' else 'de'],'latest_answer':text},ensure_ascii=False)})
        try:
            packet=self.call(messages,TURN_SCHEMA,validate,600)
        except (ValueError,KeyError,TypeError) as error:
            if self.language=='en':raise
            # A bounded failure can safely advance using the existing bank; no fabricated content.
            self.validation_warnings.append({'question_id':current['id'],'action':'bank_question_fallback','reason':str(error)})
            packet={'acknowledgement':{'de':'Danke.','fr':'Merci.','it':'Grazie.'}[self.language],
                    'question':question_text(next_q,self.language) if next_q else '',
                    'followup':False,'reason':'Two invalid model outputs; deterministic bank fallback.'}

        if not packet['followup'] and next_q and self.language!='en':
            packet['question']=question_text(next_q,self.language)
        # Main-question content is controller-owned; strip duplicate questions from acknowledgement.
        packet['acknowledgement']=' '.join(x for x in re.split(r'(?<=[.!?])\s+',packet['acknowledgement']) if '?' not in x)
        if current['type']=='smalltalk':
            packet['acknowledgement']={'de':'Danke.','fr':'Merci.','it':'Grazie.','en':'Thank you.'}[self.language]
        if packet['followup'] and next_q:
            self.current_followups+=1;self.followup_count+=1
        else:
            topic=current['flow_stage']+':'+current['subtopic']
            if topic not in self.covered_topics:self.covered_topics.append(topic)
            if next_q:
                self.index+=1;self.current_followups=0;self.main_question_count+=1;self.set_question(next_q)
        reply=' '.join(x.strip() for x in (packet['acknowledgement'],packet['question']) if x.strip())
        if reply:self.transcript.append({'role':'assistant','content':reply,'question_id':self.plan[self.index]['id'],'stage':self.current_stage,'followup':packet['followup']})
        if not next_q:
            self.roleplay_finished=True
            return self.finish()
        return {'reply':reply,'hint':'','complete':False,'can_continue':True,'suggest_recap':False,'state':self.state()}

    def finish(self):
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
