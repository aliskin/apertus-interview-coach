"""Multilingual hybrid interview: code owns actions; quoted evidence separates assessment and learning."""
import copy
import json
import re
import interview_controller as c

TEXT=json.loads((c.PROMPTS/'hybrid_ui.json').read_text())
def local_text(language,key):return TEXT[language][key]


def obj(properties):
    return {'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}
STR={'type':'string'}
def array(items, maximum=3):return {'type':'array','items':items,'maxItems':maximum}
def prompt(name,language='de'):
    if language not in c.GUIDANCE:raise ValueError('Unsupported hybrid language.')
    return (c.PROMPTS/f'hybrid_{name}.{language}.txt').read_text()
def messages(name,data,language='de'):return [{'role':'system','content':prompt(name,language)},{'role':'user','content':json.dumps(data,ensure_ascii=False)}]
def evidence_kind(q,quote):
    return 'hypothetical' if q['type']=='situational' or q['subtopic']=='group_task' or re.search(r'\b(würde|würden)\b',quote,re.I) else 'reported'

def normal(text):return re.sub(r'[^\w]+',' ',text.casefold()).strip()
def safe_acknowledgement(text):
    if re.search(r'ich.{0,20}(schicke|sende|bestätige|garantiere)|ich.{0,20}liste.{0,20}zu',text,re.I):return 'Danke für die Erklärung.'
    return text

def join_reply(ack,question):
    ack=safe_acknowledgement(ack).strip()
    if ack and question and ack[-1] not in '.!?:;':ack+='.'
    return ' '.join(x for x in (ack,question) if x)

def normalise_unassessed(item,language='de'):
    if item['score'] is None and item['explanation'] != local_text(language,'Die Auswertung ist nicht verlässlich verfügbar. Wir zeigen deshalb keine Bewertung.'):
        item['explanation']=local_text(language,'Auftreten, Körpersprache und Stimme können wir aus Text nicht beurteilen.') if item['key']=='demeanor' else local_text(language,'Das konnten wir in dieser Übung nicht ausreichend beurteilen.')
    return item

def parts(text):return list(dict.fromkeys([text.strip()]+[x.strip() for x in re.split(r'(?<!\d\.)(?<!St\.)(?<!z\.B\.)(?<=[.!?])\s+',text) if x.strip()]))
def strong_doubt(text):
    # Conservative text trigger backs up the model; not a diagnosis or a detector for all distress.
    for quote in parts(text)[1:]+[text]:
        if re.fullmatch(r'\s*Ich (?:zweifle nicht an mir|habe keine Angst, dass ich nicht gut genug bin)[.!]?\s*',quote,re.I):continue
        if re.search(r'ich.{0,55}(zweifl\w*|zweifel\w*).{0,25}(an mir|an mich)|ich.{0,55}(nicht|nöd|ned|nöd so|nicht so).{0,12}schlau|ich.{0,65}(nicht|nöd|ned).{0,12}gut genug|ich.{0,30}(traue|trau).{0,20}(nicht|nöd|ned).{0,10}zu|niemand.{0,15}(nimmt|will).{0,10}mich|ich.{0,40}(eh|sowieso).{0,20}(nüt|nicht).{0,15}pass',quote,re.I):return quote
    return ''

def benign_support_quote(quote):
    """Exclude clearly ordinary nerves/positive descriptions, not unfamiliar concern wording."""
    if re.fullmatch(r'\s*Ich (?:zweifle nicht an mir|habe keine Angst, dass ich nicht gut genug bin)[.!]?\s*',quote,re.I):return True
    if strong_doubt(quote):return False
    if re.fullmatch(r'\s*Ich bin (?:ein bisschen |etwas |leicht |noch |ziemlich |sehr |nicht )?nervös[.!]?\s*',quote,re.I):return True
    if re.search(r'angst|sorg|zweifel|unsicher|überforder|belast|zutrau|traue|nicht|nöd|ned|ablehn|absag',quote,re.I):return False
    return bool(re.search(r'ich (?:helfe|kümmere|koche|spiele|arbeite gerne)|verantwortung|mein hobby|schnupper|interessiert mich',quote,re.I))


def analyse(s,text,q):
    excerpts=parts(text);known={r['record_id']:r for r in s.evidence_records}
    quoted={'type':'string','enum':excerpts}
    schema=obj({'quotes':array(quoted),'status':{'type':'string','enum':['sufficient','gap','unclear']},'gap':STR,
                'requests':array(quoted),'support_quote':{'type':'string','enum':['']+excerpts},
                'resolves':array({'type':'string','enum':['']+list(known)}),
                'conflicts':array({'type':'string','enum':['']+list(known)})})
    if s.conversation_policy=='connected':
        remaining=[x for x in s.plan[s.index+1:] if x['flow_stage'] not in ('candidate_questions','closing')]
        schema['properties'].update({'covered_questions':array(obj({'question_id':{'type':'string','enum':[x['id'] for x in remaining] or ['']},'quote':quoted,'confidence':{'type':'string','enum':['certain','uncertain']}}),2),'related_question_id':{'type':'string','enum':['']+[x['id'] for x in remaining]},'concern_quote':{'type':'string','enum':['']+excerpts}})
        schema['required']=list(schema['properties'])
    position=len(s.transcript)-1 if s.transcript and s.transcript[-1]['role']=='user' else len(s.transcript)
    data={'question':c.answered_question_context(s.transcript,position,q,'de'),'answer':text,'occupation':s.posting['occupation']['name_de'],
          'evidence_records':s.evidence_records,'dialogue':s.transcript,'experience':s.experience,'difficulty':s.difficulty,'prior_learning_targets':s.prior_learning_targets}
    if s.conversation_policy=='connected':data['remaining_questions']=[c.question_context(x,'de') for x in remaining]
    def validate(p):
        if s.conversation_policy=='connected':
            for item in p.get('covered_questions',[]):
                if item['question_id'] not in [x['id'] for x in remaining] or item['quote'] not in text:raise ValueError('Invalid coverage evidence')
            if p.get('concern_quote') and p['concern_quote'] not in text:raise ValueError('Invalid concern quote')
        if set(p)!=set(schema['required']) or p['status'] not in ('sufficient','gap','unclear'):raise ValueError('Invalid analysis.')
        if not isinstance(p['gap'],str):raise ValueError('Invalid gap.')
        for key in ('quotes','requests'):
            if not isinstance(p[key],list) or len(p[key])>3 or any(not isinstance(x,str) or not x or x not in text for x in p[key]):raise ValueError('Quote absent.')
        if not isinstance(p['support_quote'],str) or (p['support_quote'] and p['support_quote'] not in text):raise ValueError('Support quote absent.')
        for key in ('resolves','conflicts'):
            if not isinstance(p[key],list) or any(r not in known for r in p[key]):raise ValueError('Unknown evidence ID.')
            if p[key] and not p['quotes']:raise ValueError('Memory update has no evidence.')
        if any(not known[r]['open_gap'] for r in p['resolves']):raise ValueError('Only open gaps can be resolved.')
        if p['status']=='sufficient':p['gap']=''
        elif not p['gap'].strip():raise ValueError('Clarification needs a specific gap.')
        if re.search(r'\b(?:record_id|evidence_id|related_question_id|covered_questions|(?:json|response|output)[ _-]schema|json[ _-](?:feld|field))\b',p['gap'],re.I):raise ValueError('Internal bookkeeping is not a candidate gap.')
    try:p=s.call(messages('connected_analysis' if s.conversation_policy=='connected' else 'analysis',data),schema,validate,1400,task='analysis',reserve=2)
    except (ValueError,KeyError,TypeError) as e:
        s.validation_warnings.append({'action':'analysis_unavailable','reason':str(e)});p={'quotes':[],'status':'sufficient','gap':'','requests':[],'support_quote':'','resolves':[],'conflicts':[],'unavailable':True}
    p['quotes']=list(dict.fromkeys(p['quotes']));p['requests']=list(dict.fromkeys(p['requests']))
    model_support=p['support_quote']
    p['support_quote']=strong_doubt(text) or model_support
    if p['support_quote'] and benign_support_quote(p['support_quote']):p['support_quote']=''
    # Recover explicit company questions missed by analysis; do not treat rhetorical questions as requests.
    for quote in parts(text)[1:]+[text]:
        if len(quote)>600:continue
        if ('?' in quote and re.search(r'\b(wie|was|welche|gibt|brauche|lernen|dürfen|ist|wird)\b',quote,re.I) and re.search(r'\b(euch|eure?\w*|bei uns|bei ihnen|ausbildung|lehre|unterlagen|auswahlprozess|produktschulung|wochenende|bm|betrieb|werkstatt)\b',quote,re.I)) or re.search(r'bitte sag|möchte.{0,12}wissen|würde gerne wissen|w[öo]le.{0,12}wiss',quote,re.I):
            if quote not in p['requests'] and len(p['requests'])<3:p['requests'].append(quote)
    rid=f'answer-{s.answers}'
    kind='hypothetical' if q['type']=='situational' or q['id'].startswith('Q-SIT-') else 'reported'
    evidence=[{'quote':quote,'statement':quote,'kind':evidence_kind(q,quote),'evidence_id':f'{rid}:quote-{i+1}'} for i,quote in enumerate(p['quotes'])]
    record={'record_id':rid,'turn_id':f'candidate-{s.answers}','question_id':q['id'],'topic':q['flow_stage']+':'+q['subtopic'],
            'criteria':q['criteria'],'evidence':evidence,'open_gap':p['gap'],'clarified_by':[],'possible_conflict':[]}
    if p.get('unavailable'):record['uncertainty']='analysis_unavailable'
    for rid_old in p['resolves']:
        known[rid_old]['original_gap']=known[rid_old]['open_gap'];known[rid_old]['open_gap']='';known[rid_old]['clarified_by'].append(rid)
    for rid_old in p['conflicts']:
        known[rid_old]['possible_conflict'].append(rid);record['possible_conflict'].append(rid_old)
    s.evidence_records.append(record)
    result={'answer':s.answers,'question_id':q['id'],'answer_status':{'sufficient':'answered','gap':'partial','unclear':'unanswered'}[p['status']],
            'missing_information':p['gap'],'observations':evidence,'support_quote':p['support_quote'],
            'company_question_quote':'\n'.join(p['requests']),'requests':p['requests'],'resolved_record_ids':p['resolves'],'conflict_record_ids':p['conflicts']}
    result.update({k:p.get(k,[] if k=='covered_questions' else '') for k in ('covered_questions','related_question_id','concern_quote')})
    s.answer_analyses.append(result);refresh_coverage(s);return result


def refresh_coverage(s):
    # Coverage is evidence availability, never a competence score.
    for criterion in c.RUBRIC['criteria']:
        key=criterion['key'];records=[r for r in s.evidence_records if key in r.get('criteria',[]) and key!='demeanor' and (key!='difficult_questions' or c.QUESTIONS[r['question_id']]['flow_stage']=='situational')]
        refs=[e['evidence_id'] for r in records for e in r['evidence']]
        s.competencies[key]={'status':'unassessed' if not refs else 'partial' if any(r['open_gap'] for r in records) else 'evidence_available','evidence_ids':refs}


def posting_facts(posting):
    result={}
    def walk(value,path):
        if isinstance(value,dict):
            for k,v in value.items():walk(v,path+'.'+k if path else k)
        elif isinstance(value,list):
            for i,v in enumerate(value):walk(v,f'{path}[{i}]')
        elif isinstance(value,str):
            # Facts have stable paths and sentence excerpts, no invented paraphrases.
            if path=='id' or path.endswith('.id'):return
            if path.endswith(('name_fr','name_it','lang','occupation_id','berufsfeld_key')):return
            for i,quote in enumerate(re.split(r'\n+|(?<=[.!?])\s+',value)):
                if quote.strip():result[f'{path}:{i}']=quote.strip()
        elif path=='occupation.duration_years':result[path]=f'Dauer der Lehre: {value} Jahre.'
    walk(posting,'');return result


def company_reply(s,requests):
    facts=posting_facts(s.posting)
    if not requests:return 'Welche Informationen interessieren dich besonders?'
    schema=obj({'answers':array(obj({'request_quote':{'type':'string','enum':requests},'fact_ids':array({'type':'string','enum':list(facts)},3),'unavailable':{'type':'boolean'}}),3)})
    def validate(p):
        entries=p['answers']
        if any(x['request_quote'] not in requests for x in entries):raise ValueError('Unknown company request.')
        seen={x['request_quote'] for x in entries}
        entries[:]=list({x['request_quote']:x for x in entries}.values())
        entries.extend({'request_quote':q,'fact_ids':[],'unavailable':True} for q in requests if q not in seen)
        for x in entries:
            if any(k not in facts for k in x['fact_ids']):raise ValueError('Unknown posting fact.')
            if not x['fact_ids'] and not x['unavailable']:raise ValueError('Company answer has no source.')
    try:p=s.call(messages('company',{'requests':requests,'facts':facts}),schema,validate,650,task='company',reserve=2)
    except (ValueError,KeyError,TypeError) as e:
        s.validation_warnings.append({'action':'company_unavailable','reason':str(e)})
        return 'Dazu kann ich dir aus den vorliegenden Betriebsangaben keine verlässliche Antwort geben.'
    selected=list(dict.fromkeys(k for x in p['answers'] for k in x['fact_ids']))
    s.company_answers.append({'answer':s.answers,'requests':requests,'answers':p['answers'],'facts':{k:facts[k] for k in selected}})
    text=' '.join(facts[k] for k in selected)
    if any(x['unavailable'] for x in p['answers']):text+=' Für die übrigen Details fehlen mir verlässliche Betriebsangaben; frage diese bitte beim Betrieb nach.'
    return text.strip()


def speak(s,text,q,nxt,action,gap):
    data={'recent_reactions_do_not_copy':s.speaker_reactions[-3:],
          'action':action,'difficulty':s.difficulty,'experience':s.experience,
          'next_stage':nxt['flow_stage'] if nxt else 'feedback',
          'next_question':c.question_context(nxt,'de') if nxt else None,
          'current_question':c.answered_question_context(s.transcript,len(s.transcript)-1 if s.transcript and s.transcript[-1]['role']=='user' else len(s.transcript),q,'de'),'gap':gap,
          'current_candidate_answer':text}
    schema=obj({'acknowledgement':STR,'question':STR if action=='clarify' else {'type':'string','enum':['']}})
    def validate(p):
        ack=p['acknowledgement'];follow=p['question']
        if not isinstance(ack,str) or not isinstance(follow,str) or len(ack.split())>22:raise ValueError('Invalid acknowledgement.')
        if '?' in ack or re.search(r'(^|[.!]\s+)(Erzähl|Nenne|Beschreib|Kannst|Wie |Was |Welche |Warum )',ack):raise ValueError('Question inside acknowledgement.')
        if re.search(r'\bdank(?:e|eschön)\b|\bzeig(?:t|en|st)\b|genau das.{0,20}brauchen|zuverlässig|teamfähig|berufseignung|beeindruck|klar erkennbar|gut gemacht|passt.{0,20}(uns|unser|ausbildung|pixelfabrik)|lernwill|selbstreflexion',ack,re.I):raise ValueError('Competence praise inside acknowledgement.')
        if action=='clarify':
            if not follow or len(follow.split())>25 or follow.count('?')!=1:raise ValueError('One short clarification required.')
            if normal(follow) in [normal(text) for item in s.plan for text in c.approved_question_variants(item,'de')] or c.question_repeated(follow,s.transcript,'de'):raise ValueError('Repeated/planned clarification.')
        elif follow.strip():raise ValueError('Only code selects the next question.')
    try:
        p=s.call(messages('speaker',data),schema,validate,380,task='speaker',reserve=2);ack=p['acknowledgement'];question=p['question']
        if ack.strip() and any(normal(ack)==normal(old) for old in s.speaker_reactions[-3:]):
            s.validation_warnings.append({'action':'repeated_acknowledgement_omitted','reason':ack});ack=''
        s.speaker_reactions.append(ack)
    except (ValueError,KeyError,TypeError) as e:
        s.validation_warnings.append({'action':'speaker_bank_fallback','reason':str(e)});ack='';question='';action='advance'
    return ack,question,action


def answer(s,text,recap=False):
    if s.conversation_policy=='connected':
        import connected
        return connected.answer(s,text,recap)
    if s.complete:raise ValueError('Session is complete.')
    if text:
        if not isinstance(text,str) or not text.strip() or len(text)>4000:raise ValueError('Invalid answer.')
        s.record_answer(text)
    elif not recap:raise ValueError('An answer is required.')
    if recap:return finish(s)
    q=s.plan[s.index];nxt=s.plan[s.index+1] if s.index+1<len(s.plan) else None
    a=analyse(s,text,q);action='advance';ack='';question=''
    if a['support_quote']:
        action='support';s.conversation_state='support'
        ack=('Wir können uns Zeit nehmen. Du darfst hier üben, ohne etwas beweisen zu müssen.' if s.support_offered else 'Absagen können weh tun. Sie sagen nicht, was du als Person wert bist. Sprich mit einer vertrauten erwachsenen Person oder der Berufsberatung darüber. Hier darfst du in Ruhe üben; du musst nichts beweisen.')
        s.support_offered=True
        if a['requests']:ack+=' '+company_reply(s,a['requests'])
    elif a['requests']:
        action='answer_company';s.conversation_state='company_question';ack=company_reply(s,a['requests'])
    else:
        allowed=bool(nxt and not s.current_followups and q['flow_stage'] not in ('candidate_questions','closing') and q['type']!='smalltalk' and q['subtopic'] not in ('tech_check','call_opening'))
        action='clarify' if allowed and a['missing_information'] else 'advance'
        s.conversation_state='clarification' if action=='clarify' else 'interview'
        if q['flow_stage']=='closing':ack='Danke für das Gespräch.'
        else:
            ack,question,action=speak(s,text,q,nxt,action,a['missing_information'])
    s.turn_decisions.append({'answer':s.answers,'question_id':q['id'],'action':action,'analysis_index':len(s.answer_analyses)-1})
    if action=='clarify':s.current_followups+=1;s.followup_count+=1
    else:
        topic=q['flow_stage']+':'+q['subtopic']
        if topic not in s.covered_topics:s.covered_topics.append(topic)
        if nxt:
            s.index+=1;s.current_followups=0;s.main_question_count+=1;s.set_question(nxt);question=c.question_text(nxt,'de')
            if action=='support':ack+=' Wenn du weiterüben möchtest:'
    reply=join_reply(ack,question)
    if reply:s.transcript.append({'role':'assistant','content':reply,'question_id':s.plan[s.index]['id'],'stage':s.current_stage,'actual_question':question,'followup':action=='clarify','action':action})
    if not nxt and action!='clarify':s.roleplay_finished=True;return finish(s)
    return {'reply':reply,'hint':'','complete':False,'can_continue':True,'suggest_recap':False,'state':s.state()}


def eligible_evidence(s):
    # Rebuild from the actual transcript too: early recap must not lose its last unanalysed answer.
    result={k['key']:{} for k in c.RUBRIC['criteria']}
    candidates=[(pos,t) for pos,t in enumerate(s.transcript) if t['role']=='user' and t.get('phase')!='practice']
    for i,(position,t) in enumerate(candidates):
        q=c.QUESTIONS.get(t.get('question_id'))
        if not q:continue
        kind='hypothetical' if q['id'].startswith('Q-SIT-') or q['type']=='situational' else 'reported'
        for j,quote in enumerate(parts(t['content'])[1:] or parts(t['content'])):
            eid=f'candidate-{i+1}:quote-{j+1}'
            for key in q['criteria']:
                if key=='difficult_questions' and q['flow_stage']!='situational' and q['type']!='difficult':continue
                if key=='demeanor':continue # Text is not observed body language or vocal delivery.
                result[key][eid]={'quote':quote,'kind':evidence_kind(q,quote),'question_id':q['id'],'turn_id':f'candidate-{i+1}','actual_question':c.answered_question_context(s.transcript,position,q,s.language)['text']}
    return result


def no_improvement():
    return {'usefulness':'unnecessary','missing_detail':'','why_needed':'','already_supplied':False,'expected_outcome':'','question_id':''}

def full_answers(s):
    answers=[]
    for position,turn in enumerate(s.transcript):
        if turn['role']!='user' or turn.get('phase')=='practice':continue
        question=c.QUESTIONS.get(turn.get('question_id'))
        if question is None:continue
        answers.append({'turn_id':f'candidate-{len(answers)+1}',
                        'question':c.answered_question_context(s.transcript,position,question,s.language),
                        'answer':turn['content']})
    return answers


def validate_improvement(p,evidence,score):
    if set(p)!=set(no_improvement()) or p['usefulness'] not in ('useful','unnecessary','uncertain') or type(p['already_supplied']) is not bool:raise ValueError('Invalid improvement proposal.')
    for key in ('missing_detail','why_needed','expected_outcome','question_id'):
        if not isinstance(p[key],str) or len(p[key].split())>45:raise ValueError('Invalid improvement text.')
    if p['usefulness']=='useful':
        if score is None or p['already_supplied'] or not all(p[k].strip() for k in ('missing_detail','why_needed','expected_outcome')):raise ValueError('Useful improvement needs an unfilled relevant gap.')
        if p['question_id'] not in {e['question_id'] for e in evidence.values()}:raise ValueError('Improvement question absent.')
    elif any(p[k] for k in ('missing_detail','why_needed','expected_outcome')):raise ValueError('No speculative gap for unnecessary/uncertain proposal.')

def verify_improvements(s,criteria):
    labels={x['key']:x['label'][s.language] for x in c.RUBRIC['criteria']}
    proposals=[{'target_id':'gap:'+x['key'],'key':x['key'],'label':labels[x['key']], 'score':x['score'],
                'evidence_records':x['evidence_records'],**x['improvement']} for x in criteria if x['improvement']['usefulness']=='useful']
    if not proposals:return [],{},None
    ids=[x['target_id'] for x in proposals]
    all_evidence={k:v for values in eligible_evidence(s).values() for k,v in values.items()}
    schema=obj({'checks':obj({tid:obj({'decision':{'type':'string','enum':['supported','contradicted','uncertain']},'reason':STR,
                                     'evidence_ids':array({'type':'string','enum':['']+list(all_evidence)},2)}) for tid in ids})})
    def validate(p):
        if set(p['checks'])!=set(ids):raise ValueError('Exactly all proposal IDs required.')
        for item in p['checks'].values():
            if item['decision'] not in ('supported','contradicted','uncertain') or not isinstance(item['reason'],str) or not item['reason'].strip() or len(item['reason'].split())>35:raise ValueError('Invalid verification explanation.')
            if any(e not in all_evidence for e in item['evidence_ids']):raise ValueError('Verification evidence absent.')
    try:checks=s.call(messages('verify',{'proposals':proposals,'answers':full_answers(s),'evidence':all_evidence},s.language),schema,validate,2600,task='verify',reserve=1)['checks']
    except (ValueError,KeyError,TypeError) as e:
        s.validation_warnings.append({'action':'verification_unavailable','reason':str(e)})
        checks={tid:{'decision':'uncertain','reason':local_text(s.language,'Die Gegenprüfung ist nicht verlässlich verfügbar.'),'evidence_ids':[]} for tid in ids}
    for proposal in proposals:
        check=checks[proposal['target_id']]
        check['evidence_records']=[dict(evidence_id=e,**all_evidence[e]) for e in check['evidence_ids']]
        item=next(x for x in criteria if x['key']==proposal['key'])
        item['improvement']['verification_decision']=check['decision']
        if check['decision']!='supported' and (item['score'] is None or item['score']<=2 or item.get('assessment_depends_on_gap',True)):
            # Negative/dependent assessments still fail closed; independent positives survive.
            item['score']=None;item['evidence']='';item['evidence_records']=[]
            item['explanation']=local_text(s.language,'Diese Einschätzung wurde bei der Gegenprüfung nicht bestätigt. Deshalb zeigen wir dafür keine Bewertung.')
    approved=[p for p in proposals if checks[p['target_id']]['decision']=='supported']
    return proposals,checks,min(approved,key=lambda p:p['score']) if approved else None

def optional_choices(criteria,language='de',available=None):
    labels={x['key']:x['label'][language] for x in c.RUBRIC['criteria']}
    priority=['motivation','self_reflection','clarity','preparation','communication','concrete_examples']
    priority+= [key for key in labels if key not in priority and key!='demeanor']
    choices=[]
    for key in priority:
        item=next((x for x in criteria if x['key']==key),None)
        if item is None:continue
        evidence=list((available or {}).get(key,{}).values()) or item.get('evidence_records',[])
        if not evidence and item.get('score') is None:continue
        choice={'target_id':'optional:'+key,'key':key,'label':labels[key]}
        if evidence:choice['question_id']=evidence[0]['question_id']
        choices.append(choice)
    return choices[:3]


def learn(s,target,optional=False):
    tid=target['target_id']
    schema=obj({'target_id':{'type':'string','enum':[tid]},**{k:STR for k in ('explanation','exercise','reflection','revision_prompt','encouragement')}})
    def validate(p):
        if set(p)!=set(schema['required']) or p['target_id']!=tid or any(not isinstance(v,str) for v in p.values()):raise ValueError('Learning target ID mismatch.')
        if any(not p[k].strip() for k in ('exercise','reflection','revision_prompt','encouragement')):raise ValueError('Learning target needs an exercise, reflection and revision invitation.')
        if len(p['exercise'].split())>35 or len(p['explanation'].split())>55 or p['reflection'].count('?')!=1:raise ValueError('Learning response too long or invalid reflection.')
    try:return s.call(messages('learning',{'target':target,'optional_practice':optional,'difficulty':s.difficulty,'experience':s.experience},s.language),schema,validate,750,task='learning')
    except (ValueError,KeyError,TypeError) as e:
        s.validation_warnings.append({'action':'learning_unavailable','reason':str(e)})
        return {'target_id':tid,'explanation':local_text(s.language,'Die Lernempfehlung ist gerade nicht verfügbar.'),'exercise':'','reflection':'','revision_prompt':'','encouragement':local_text(s.language,'Danke für die Übung. Du kannst in deinem Tempo weiterlernen.')}

def choose_practice(s,target_id):
    if not s.complete or not s.feedback:raise ValueError('Finish the interview before choosing practice.')
    choice=next((x for x in s.feedback.get('optional_practice_choices',[]) if x['target_id']==target_id),None)
    if choice is None:raise ValueError('Unknown optional practice target.')
    item=next(x for x in s.feedback['criteria'] if x['key']==choice['key'])
    target={**choice,'evidence_records':copy.deepcopy(item.get('evidence_records',[])),'missing_detail':'','why_needed':local_text(s.language,'Freiwillige Wahl der Person, kein festgestellter Mangel.'),'expected_outcome':local_text(s.language,'Die gewählte Antwort in eigenen Worten üben.')}
    # Do not leak rejected gaps, ratings or unverified assessment explanations into practice.
    # An unassessed topic can still be practised voluntarily; retain the actual answer.
    answers=full_answers(s)
    qid=choice.get('question_id') or next((e['question_id'] for e in item.get('evidence_records',[])),None)
    original=next((a for a in answers if a['question']['id']==qid),None)
    if original:target.update(question=original['question'],original_answer=original['answer'])
    learning=learn(s,target,optional=True)
    if learning['exercise']:
        target.update(exercise=learning['exercise'],reflection=learning['reflection'],revision_prompt=learning['revision_prompt'],previous_answer=target.get('original_answer',''))
    s.learning_target=target if learning['exercise'] else None
    if s.learning_target:s.practice_history.append({'target_id':target_id,'criterion':target['key'],'exercise':learning['exercise'],'evidence':target['evidence_records'],'optional':True})
    reply='\n\n'.join(learning[k] for k in ('explanation','exercise','reflection','revision_prompt','encouragement') if learning[k])
    s.transcript.append({'role':'assistant','content':reply,'stage':'feedback','phase':'practice','action':'practice_assignment','target_id':target_id})
    return {'reply':reply,'complete':True,'state':s.state(),'can_revise':bool(s.learning_target),'optional_practice_choices':s.feedback['optional_practice_choices']}


def finish(s):
    if not s.answers:raise ValueError('Answer at least one question before requesting feedback.')
    s.recap_attempts+=1;s.roleplay_finished=True;s.recap_status='pending'
    candidates=[t for t in s.transcript if t['role']=='user' and t.get('phase')!='practice']
    if candidates and all(c.QUESTIONS.get(t.get('question_id'),{}).get('type')=='smalltalk' for t in candidates):
        # An arrival/greeting answer is not a substantive interview assessment.
        criteria=[dict(key=x['key'],score=None,evidence='',evidence_records=[],explanation=local_text(s.language,'Dieses Kriterium haben wir beim kurzen Einstieg noch nicht geprüft.'),next_step='') for x in c.RUBRIC['criteria']]
        learning=dict(explanation=local_text(s.language,'Wir haben bisher nur den kurzen Einstieg geübt. Für eine inhaltliche Rückmeldung brauchen wir weitere Interviewfragen.'),exercise='',reflection='',revision_prompt='',encouragement=local_text(s.language,'Danke fürs Üben. Du kannst beim nächsten Mal in deinem Tempo weitergehen.'))
        s.feedback=dict(summary=learning['explanation'],closing=learning['encouragement'],criteria=criteria,learning=learning,improvement_proposals=[],verification={},optional_practice_choices=[])
        s.learning_target=None;s.complete=True;s.recap_status='complete';s.current_stage='feedback';s.question_subtype='session_recap';s.conversation_state='reflection'
        text=learning['explanation']+'\n\n'+learning['encouragement'];s.transcript.append({'role':'assistant','content':text,'stage':'feedback'})
        return {'reply':text,'hint':'','complete':True,'can_continue':False,'suggest_recap':False,'state':s.state(),'feedback':s.feedback,'can_revise':False}
    allowed=eligible_evidence(s);keys=list(allowed)
    remaining=5*(s.answers+s.practice_answers)-1-s.model_calls
    batch_count=1 if s.answers<3 else min(11,max(1,remaining-2))
    groups=[keys[i::batch_count] for i in range(batch_count)]
    assessed_packets={};attempted_groups=0;successful_groups=0
    for group_number,group in enumerate(groups):
        if not any(allowed[key] for key in group):
            assessed_packets.update({key:dict(score=None,evidence_ids=[],explanation=local_text(s.language,'Das konnten wir in dieser Übung nicht ausreichend beurteilen.'),improvement=no_improvement()) for key in group})
            continue
        question_ids=list(dict.fromkeys(e['question_id'] for key in group for e in allowed[key].values()))
        improvement_schema=obj({'criterion_key':{'type':'string','enum':group},'usefulness':{'type':'string','enum':['useful']},
            'missing_detail':STR,'why_needed':STR,'already_supplied':{'type':'boolean','enum':[False]},'expected_outcome':STR,
            'question_id':{'type':'string','enum':question_ids or ['']}})
        schema=obj({'criteria':obj({key:obj({'score':{'type':['integer','null'],'enum':[None,1,2,3,4]},
                 'evidence_ids':array({'type':'string','enum':['']+list(allowed[key])},2),'explanation':STR,'assessment_depends_on_gap':{'type':'boolean'}}) for key in group}),
                 'improvements':array(improvement_schema,2)})
        for key in group:
            if not allowed[key]:
                schema['properties']['criteria']['properties'][key]['properties']['score']['enum']=[None]
                schema['properties']['criteria']['properties'][key]['properties']['evidence_ids']['maxItems']=0
        def validate(p):
            if set(p['criteria'])!=set(group):raise ValueError('Exactly the requested criteria required.')
            for key,item in p['criteria'].items():
                ids=item['evidence_ids'];score=item['score']
                if any(e not in allowed[key] for e in ids):raise ValueError('Evidence not eligible for criterion.')
                if (score is None and ids) or (score is not None and not ids):raise ValueError('Assessment needs criterion evidence.')
                if score is not None and (type(score)!=int or score not in (1,2,3,4)):raise ValueError('Invalid score.')
                if not isinstance(item['explanation'],str) or len(item['explanation'].split())>55:raise ValueError('Explanation too long.')
                if 'assessment_depends_on_gap' in item and type(item['assessment_depends_on_gap']) is not bool:raise ValueError('Invalid assessment dependency.')
                item['improvement']=no_improvement()
            if not isinstance(p['improvements'],list) or len(p['improvements'])>2:raise ValueError('At most two concrete proposals per group.')
            for proposed in p['improvements']:
                key=proposed.get('criterion_key');improvement={k:v for k,v in proposed.items() if k!='criterion_key'}
                try:
                    if key not in group:raise ValueError('Proposal criterion absent.')
                    validate_improvement(improvement,allowed[key],p['criteria'][key]['score'])
                    if p['criteria'][key]['improvement']['usefulness']=='useful':raise ValueError('Duplicate proposal criterion.')
                    p['criteria'][key]['improvement']=improvement
                except (ValueError,KeyError,TypeError) as e:
                    s.validation_warnings.append({'action':'proposal_discarded','criterion':key,'reason':str(e)})
        data={'rubric':[x for x in c.GUIDANCE[s.language]['rubric'] if x['key'] in group],
              'feedback_guidelines':c.GUIDANCE[s.language]['guidelines'],
              'allowed_evidence':{key:allowed[key] for key in group},
              'answers':full_answers(s), 'other_answers_are_context_only':True}
        attempted_groups+=1
        future=sum(any(allowed[key] for key in later) for later in groups[group_number+1:])
        available=5*(s.answers+s.practice_answers)-1-s.model_calls
        reserve=min(future+2,max(0,available-1))
        try:
            p=s.call(messages('evaluator',data,s.language),schema,validate,3000 if batch_count>1 else 6500,task='evaluator',reserve=reserve)
            successful_groups+=1
        except (ValueError,KeyError,TypeError,RuntimeError,OSError) as e:
            s.validation_warnings.append({'action':'evaluation_unavailable','criteria':group,'reason':str(e)});p={'criteria':{k:{'score':None,'evidence_ids':[],'explanation':local_text(s.language,'Die Auswertung ist nicht verlässlich verfügbar. Wir zeigen deshalb keine Bewertung.'),'improvement':no_improvement()} for k in group}}
        assessed_packets.update(p['criteria'])
    if attempted_groups and not successful_groups:
        s.complete=False;s.feedback=None;s.learning_target=None;s.recap_status='unavailable'
        s.current_stage='feedback';s.question_subtype='session_recap';s.conversation_state='recap_pending'
        retryable=s.model_calls<5*(s.answers+s.practice_answers)-1
        key='Die Zusammenfassung ist gerade nicht verfügbar. Deine Interviewantworten sind gespeichert. Bitte versuche die Zusammenfassung erneut.' if retryable else 'Die Zusammenfassung ist nicht verfügbar und das Anfragebudget ist aufgebraucht. Deine Interviewantworten bleiben gespeichert. Du kannst sie herunterladen oder eine neue Übung starten.'
        text=local_text(s.language,key)
        s.transcript.append({'role':'assistant','content':text,'stage':'feedback','action':'recap_unavailable'})
        return {'reply':text,'hint':'','complete':False,'can_continue':False,'suggest_recap':retryable,'recap_retryable':retryable,'state':s.state(),'can_revise':False,'optional_practice_choices':[]}
    s.recap_status='partial' if successful_groups<attempted_groups else 'complete'
    p={'criteria':{key:assessed_packets[key] for key in keys}}
    criteria=[]
    for key,item in p['criteria'].items():
        evidence=[dict(evidence_id=e,**allowed[key][e]) for e in item['evidence_ids']]
        criteria.append(normalise_unassessed(dict(key=key,score=item['score'],evidence='\n'.join(e['quote'] for e in evidence),evidence_records=evidence,explanation=item['explanation'],next_step='',improvement=item['improvement'],assessment_depends_on_gap=item.get('assessment_depends_on_gap',True)),s.language))
    for item in criteria:
        if item['score'] is not None and item['score']<=2 and item['improvement']['usefulness']!='useful':
            s.validation_warnings.append({'action':'low_score_without_gap','criterion':item['key']})
            item['score']=None;item['evidence']='';item['evidence_records']=[]
            item['explanation']=local_text(s.language,'Für eine niedrigere Einschätzung fehlt eine konkrete, überprüfbare Lücke. Deshalb zeigen wir dafür keine Bewertung.')
    proposals,verification,_=verify_improvements(s,criteria)
    # No model decision assigns practice: only an explicit user selection can do so.
    s.learning_target=None
    learning={'explanation':local_text(s.language,'Wenn du freiwillig weiterüben möchtest, wähle unten ein Thema. Das ist keine festgestellte Schwäche.'),
              'exercise':'','reflection':'','revision_prompt':'','encouragement':local_text(s.language,'Danke fürs Üben. Du kannst in deinem Tempo weiterlernen.')}
    choices=optional_choices(criteria,s.language,allowed)
    assessed=[x for x in criteria if x['score'] is not None]
    s.feedback={'summary':learning['explanation'],'closing':learning['encouragement'],'criteria':criteria,'learning':learning,'improvement_proposals':proposals,'verification':verification,'optional_practice_choices':choices}
    strengths=[x for x in assessed if x['score']>=3]
    best=max(strengths,key=lambda x:x['score']) if strengths else None
    labels={x['key']:x['label'][s.language] for x in c.RUBRIC['criteria']}
    blocks=[local_text(s.language,'Was schon gelingt: ')+labels[best['key']]+'. '+best['explanation']+local_text(s.language,' Beleg: „')+best['evidence_records'][0]['quote']+'“' if best else local_text(s.language,'Danke, dass du das Gespräch geübt hast.'),learning['explanation']]
    for item,criterion in zip(criteria,c.RUBRIC['criteria']):
        block=criterion['label'][s.language]+': '+item['explanation']
        for e in item['evidence_records']:block+=local_text(s.language,'\nBeleg (')+e['question_id']+', '+(local_text(s.language,'hypothetische Antwort') if e['kind']=='hypothetical' else local_text(s.language,'deine Antwort'))+'): „'+e['quote']+'“'
        blocks.append(block)
    if learning['exercise']:blocks.append(local_text(s.language,'Freiwillige Übung: ')+learning['exercise'])
    if learning['reflection']:blocks.append(learning['reflection'])
    if learning['revision_prompt']:blocks.append(learning['revision_prompt'])
    blocks.append(learning['encouragement']);text='\n\n'.join(x for x in blocks if x)
    s.complete=True;s.current_stage='feedback';s.question_subtype='session_recap';s.conversation_state='reflection'
    s.transcript.append({'role':'assistant','content':text,'stage':'feedback'})
    return {'reply':text,'hint':'','complete':True,'can_continue':False,'suggest_recap':False,'state':s.state(),'feedback':s.feedback,'can_revise':bool(s.learning_target),'optional_practice_choices':choices}


def revise(s,text):
    if not s.complete or not s.learning_target:raise ValueError('No completed learning target to revise.')
    if not isinstance(text,str) or not text.strip() or len(text)>4000:raise ValueError('Invalid revision.')
    s.practice_answers+=1
    schema=obj({'reply':STR})
    def validate(p):
        if not isinstance(p['reply'],str) or not p['reply'].strip() or len(p['reply'].split())>65:raise ValueError('Revision feedback too long.')
    target=copy.deepcopy(s.learning_target)
    # Older saved targets may predate explicit exercise/previous-answer fields.
    if not target.get('exercise'):
        previous=next((x for x in reversed(s.practice_history) if x.get('exercise') and x.get('criterion')==target['key']),{})
        target.update({key:previous[key] for key in ('exercise','reflection','revision_prompt') if key in previous})
    previous_answer=target.get('previous_answer',target.get('original_answer',''))
    try:
        p=s.call(messages('revision',{'target':target,'previous_answer':previous_answer,'new_answer':text},s.language),schema,validate,300,task='revision')
    except (ValueError,KeyError,TypeError,RuntimeError,OSError):
        s.practice_answers-=1
        raise
    s.learning_target.update(exercise=target.get('exercise',''),previous_answer=text)
    s.practice_history.append({'target_id':target.get('target_id'),'criterion':target['key'],'exercise':target.get('exercise',''),'previous_answer':previous_answer,'revision':text,'reply':p['reply']})
    metadata={'stage':'feedback','phase':'practice','target_id':target.get('target_id'),'source_question_id':target.get('question_id',target.get('question',{}).get('id'))}
    s.transcript.extend([{'role':'user','content':text,'action':'practice_revision',**metadata},{'role':'assistant','content':p['reply'],'action':'revision_feedback',**metadata}])
    return {'reply':p['reply'],'complete':True,'state':s.state(),'practice_revision':s.practice_answers}
