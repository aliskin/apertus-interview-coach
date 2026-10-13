"""German hybrid interview: code owns actions; quoted evidence separates assessment and learning."""
import copy
import json
import re
import interview_controller as c


def obj(properties):
    return {'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}
STR={'type':'string'}
def array(items, maximum=3):return {'type':'array','items':items,'maxItems':maximum}
def prompt(name):return (c.PROMPTS/f'hybrid_{name}.de.txt').read_text()
def messages(name,data):return [{'role':'system','content':prompt(name)},{'role':'user','content':json.dumps(data,ensure_ascii=False)}]
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

def normalise_unassessed(item):
    if item['score'] is None and 'nicht verlässlich verfügbar' not in item['explanation']:
        item['explanation']='Auftreten, Körpersprache und Stimme können wir aus Text nicht beurteilen.' if item['key']=='demeanor' else 'Das konnten wir in dieser Übung nicht ausreichend beurteilen.'
    return item

def parts(text):return list(dict.fromkeys([text.strip()]+[x.strip() for x in re.split(r'(?<!\d)(?<=[.!?])\s+',text) if x.strip()]))
def strong_doubt(text):
    # Conservative text trigger backs up the model; not a diagnosis or a detector for all distress.
    for quote in parts(text)[1:]+[text]:
        if re.search(r'ich.{0,55}(zweifl\w*|zweifel\w*).{0,25}(an mir|an mich)|ich.{0,55}(nicht|nöd|ned|nöd so|nicht so).{0,12}schlau|niemand.{0,15}(nimmt|will).{0,10}mich|ich.{0,40}(eh|sowieso).{0,20}(nüt|nicht).{0,15}pass',quote,re.I):return quote
    return ''

def analyse(s,text,q):
    excerpts=parts(text);known={r['record_id']:r for r in s.evidence_records}
    quoted={'type':'string','enum':excerpts}
    schema=obj({'quotes':array(quoted),'status':{'type':'string','enum':['sufficient','gap','unclear']},'gap':STR,
                'requests':array(quoted),'support_quote':{'type':'string','enum':['']+excerpts},
                'resolves':array({'type':'string','enum':['']+list(known)}),
                'conflicts':array({'type':'string','enum':['']+list(known)})})
    position=len(s.transcript)-1 if s.transcript and s.transcript[-1]['role']=='user' else len(s.transcript)
    data={'question':c.answered_question_context(s.transcript,position,q,'de'),'answer':text,'occupation':s.posting['occupation']['name_de'],
          'evidence_records':s.evidence_records,'dialogue':s.transcript,'experience':s.experience,'difficulty':s.difficulty,'prior_learning_targets':s.prior_learning_targets}
    def validate(p):
        if set(p)!=set(schema['required']) or p['status'] not in ('sufficient','gap','unclear'):raise ValueError('Invalid analysis.')
        if not isinstance(p['gap'],str):raise ValueError('Invalid gap.')
        for key in ('quotes','requests'):
            if not isinstance(p[key],list) or len(p[key])>3 or any(not isinstance(x,str) or not x or x not in text for x in p[key]):raise ValueError('Quote absent.')
        if p['support_quote'] and p['support_quote'] not in text:raise ValueError('Support quote absent.')
        for key in ('resolves','conflicts'):
            if not isinstance(p[key],list) or any(r not in known for r in p[key]):raise ValueError('Unknown evidence ID.')
            if p[key] and not p['quotes']:raise ValueError('Memory update has no evidence.')
        if any(not known[r]['open_gap'] for r in p['resolves']):raise ValueError('Only open gaps can be resolved.')
        if p['status']=='sufficient':p['gap']=''
        elif not p['gap'].strip():raise ValueError('Clarification needs a specific gap.')
    try:p=s.call(messages('analysis',data),schema,validate,850,task='analysis',reserve=2)
    except (ValueError,KeyError,TypeError) as e:
        s.validation_warnings.append({'action':'analysis_unavailable','reason':str(e)});p={'quotes':[],'status':'sufficient','gap':'','requests':[],'support_quote':'','resolves':[],'conflicts':[],'unavailable':True}
    p['quotes']=list(dict.fromkeys(p['quotes']));p['requests']=list(dict.fromkeys(p['requests']))
    model_support=p['support_quote']
    p['support_quote']=strong_doubt(text) or (model_support if strong_doubt(model_support) else '')
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


def answer(s,text,recap=False):
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
            data={'action':action,'question':c.answered_question_context(s.transcript,len(s.transcript)-1,q,'de'),'answer':text,'gap':a['missing_information'],
                  'difficulty':s.difficulty,'experience':s.experience,'next_stage':nxt['flow_stage'] if nxt else 'feedback','previous_replies':[t['content'] for t in s.transcript if t['role']=='assistant'][-3:]}
            schema=obj({'acknowledgement':STR,'question':STR if action=='clarify' else {'type':'string','enum':['']}})
            def validate(p):
                ack=p['acknowledgement'];follow=p['question']
                if not isinstance(ack,str) or not isinstance(follow,str) or len(ack.split())>22:raise ValueError('Invalid acknowledgement.')
                if '?' in ack or re.search(r'(^|[.!]\s+)(Erzähl|Nenne|Beschreib|Kannst|Wie |Was |Welche |Warum )',ack):raise ValueError('Question inside acknowledgement.')
                if re.search(r'das zeigt|genau das.{0,20}brauchen|zuverlässig|teamfähig|berufseignung',ack,re.I):raise ValueError('Competence praise inside acknowledgement.')
                if action=='clarify':
                    if not follow or len(follow.split())>25 or follow.count('?')!=1:raise ValueError('One short clarification required.')
                    if normal(follow) in [normal(c.question_text(x,'de')) for x in s.plan] or any(normal(follow) in normal(t['content']) for t in s.transcript if t['role']=='assistant'):raise ValueError('Repeated/planned clarification.')
                elif follow.strip():raise ValueError('Only code selects the next question.')
            try:
                p=s.call(messages('speaker',data),schema,validate,260,task='speaker',reserve=2);ack=p['acknowledgement'];question=p['question']
            except (ValueError,KeyError,TypeError) as e:
                s.validation_warnings.append({'action':'speaker_bank_fallback','reason':str(e)});ack='Danke für deine Antwort.';action='advance'
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
    candidates=[(pos,t) for pos,t in enumerate(s.transcript) if t['role']=='user']
    for i,(position,t) in enumerate(candidates):
        q=c.QUESTIONS.get(t.get('question_id'))
        if not q:continue
        kind='hypothetical' if q['id'].startswith('Q-SIT-') or q['type']=='situational' else 'reported'
        for j,quote in enumerate(parts(t['content'])[1:] or parts(t['content'])):
            eid=f'candidate-{i+1}:quote-{j+1}'
            for key in q['criteria']:
                if key=='difficult_questions' and q['flow_stage']!='situational' and q['type']!='difficult':continue
                if key=='demeanor':continue # Text is not observed body language or vocal delivery.
                result[key][eid]={'quote':quote,'kind':evidence_kind(q,quote),'question_id':q['id'],'turn_id':f'candidate-{i+1}','actual_question':c.answered_question_context(s.transcript,position,q,'de')['text']}
    return result


def full_answers(s):
    answers=[]
    for position,turn in enumerate(s.transcript):
        if turn['role']!='user':continue
        question=c.QUESTIONS.get(turn.get('question_id'))
        if question is None:continue
        answers.append({'turn_id':f'candidate-{len(answers)+1}',
                        'question':c.answered_question_context(s.transcript,position,question,'de'),
                        'answer':turn['content']})
    return answers


def finish(s):
    if not s.answers:raise ValueError('Answer at least one question before requesting feedback.')
    candidates=[t for t in s.transcript if t['role']=='user']
    if candidates and all(c.QUESTIONS.get(t.get('question_id'),{}).get('type')=='smalltalk' for t in candidates):
        # An arrival/greeting answer is not a substantive interview assessment.
        criteria=[dict(key=x['key'],score=None,evidence='',evidence_records=[],explanation='Dieses Kriterium haben wir beim kurzen Einstieg noch nicht geprüft.',next_step='') for x in c.RUBRIC['criteria']]
        learning=dict(explanation='Wir haben bisher nur den kurzen Einstieg geübt. Für eine inhaltliche Rückmeldung brauchen wir weitere Interviewfragen.',exercise='',reflection='',revision_prompt='',encouragement='Danke fürs Üben. Du kannst beim nächsten Mal in deinem Tempo weitergehen.')
        s.feedback=dict(summary=learning['explanation'],closing=learning['encouragement'],criteria=criteria,learning=learning)
        s.learning_target=None;s.complete=True;s.current_stage='feedback';s.question_subtype='session_recap';s.conversation_state='reflection'
        text=learning['explanation']+'\n\n'+learning['encouragement'];s.transcript.append({'role':'assistant','content':text,'stage':'feedback'})
        return {'reply':text,'hint':'','complete':True,'can_continue':False,'suggest_recap':False,'state':s.state(),'feedback':s.feedback,'can_revise':False}
    allowed=eligible_evidence(s);keys=list(allowed)
    remaining=5*(s.answers+s.practice_answers)-1-s.model_calls
    batch_count=1 if s.answers<3 else min(3,max(1,remaining-1))
    groups=[keys[i::batch_count] for i in range(batch_count)]
    assessed_packets={}
    for group_number,group in enumerate(groups):
        schema=obj({'criteria':obj({key:obj({'score':{'type':['integer','null'],'enum':[None,1,2,3,4]},
                 'evidence_ids':array({'type':'string','enum':['']+list(allowed[key])},2),'explanation':STR}) for key in group})})
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
        data={'rubric':[x for x in c.GUIDANCE['de']['rubric'] if x['key'] in group],
              'allowed_evidence':{key:allowed[key] for key in group},
              'answers':[row for row in full_answers(s) if set(c.QUESTIONS[row['question']['id']]['criteria'])&set(group)]}
        reserve=(len(groups)-group_number-1)+1
        try:p=s.call(messages('evaluator',data),schema,validate,1200 if batch_count>1 else 2400,task='evaluator',reserve=reserve)
        except (ValueError,KeyError,TypeError) as e:
            s.validation_warnings.append({'action':'evaluation_unavailable','criteria':group,'reason':str(e)});p={'criteria':{k:{'score':None,'evidence_ids':[],'explanation':'Die Auswertung ist nicht verlässlich verfügbar. Wir zeigen deshalb keine Bewertung.'} for k in group}}
        assessed_packets.update(p['criteria'])
    p={'criteria':{key:assessed_packets[key] for key in keys}}
    criteria=[]
    for key,item in p['criteria'].items():
        evidence=[dict(evidence_id=e,**allowed[key][e]) for e in item['evidence_ids']]
        criteria.append(normalise_unassessed(dict(key=key,score=item['score'],evidence='\n'.join(e['quote'] for e in evidence),evidence_records=evidence,explanation=item['explanation'],next_step='')))
    assessed=[x for x in criteria if x['score'] is not None]
    target=min(assessed,key=lambda x:x['score']) if assessed else None
    s.learning_target=copy.deepcopy(target)
    schema_learning=obj({k:STR for k in ('explanation','exercise','reflection','revision_prompt','encouragement')})
    optional=bool(target and target['score']>=3)
    def check_learning(p):
        if set(p)!=set(schema_learning['required']) or any(not isinstance(v,str) for v in p.values()):raise ValueError('Invalid learning response.')
        if len(p['exercise'].split())>35 or len(p['explanation'].split())>55:raise ValueError('Learning response too long.')
        if p['reflection'].count('?')>1:raise ValueError('One reflection question.')
        if not target and any(p[k] for k in ('exercise','reflection','revision_prompt')):raise ValueError('No target to revise.')
    try:learning=s.call(messages('learning',{'target':target,'optional_practice':optional,'difficulty':s.difficulty,'experience':s.experience,'dialogue':s.transcript}),schema_learning,check_learning,600,task='learning')
    except (ValueError,KeyError,TypeError) as e:
        s.validation_warnings.append({'action':'learning_unavailable','reason':str(e)});learning={'explanation':'Die Lernempfehlung ist gerade nicht verfügbar.','exercise':'','reflection':'','revision_prompt':'','encouragement':'Danke für die Übung. Du kannst in deinem Tempo weiterlernen.'}
    if target:
        s.practice_history.append({'criterion':target['key'],'evidence':target['evidence_records'],'exercise':learning['exercise'],'optional':optional})
    s.feedback={'summary':learning['explanation'],'closing':learning['encouragement'],'criteria':criteria,'learning':learning}
    strengths=[x for x in assessed if x['score']>=3]
    best=max(strengths,key=lambda x:x['score']) if strengths else None
    labels={x['key']:x['label']['de'] for x in c.RUBRIC['criteria']}
    blocks=['Was schon gelingt: '+labels[best['key']]+'. '+best['explanation']+' Beleg: „'+best['evidence_records'][0]['quote']+'“' if best else 'Danke, dass du das Gespräch geübt hast.',learning['explanation']]
    for item,criterion in zip(criteria,c.RUBRIC['criteria']):
        block=criterion['label']['de']+': '+item['explanation']
        for e in item['evidence_records']:block+='\nBeleg ('+e['question_id']+', '+('hypothetische Antwort' if e['kind']=='hypothetical' else 'deine Antwort')+'): „'+e['quote']+'“'
        blocks.append(block)
    if learning['exercise']:blocks.append(('Freiwillige Übung: ' if optional else 'Nächster Schritt: ')+learning['exercise'])
    if learning['reflection']:blocks.append(learning['reflection'])
    if learning['revision_prompt']:blocks.append(learning['revision_prompt'])
    blocks.append(learning['encouragement']);text='\n\n'.join(x for x in blocks if x)
    s.complete=True;s.current_stage='feedback';s.question_subtype='session_recap';s.conversation_state='reflection'
    s.transcript.append({'role':'assistant','content':text,'stage':'feedback'})
    return {'reply':text,'hint':'','complete':True,'can_continue':False,'suggest_recap':False,'state':s.state(),'feedback':s.feedback,'can_revise':bool(target)}


def revise(s,text):
    if not s.complete or not s.learning_target:raise ValueError('No completed learning target to revise.')
    if not isinstance(text,str) or not text.strip() or len(text)>4000:raise ValueError('Invalid revision.')
    s.practice_answers+=1
    schema=obj({'reply':STR})
    def validate(p):
        if not isinstance(p['reply'],str) or len(p['reply'].split())>65:raise ValueError('Revision feedback too long.')
    p=s.call(messages('revision',{'target':s.learning_target,'new_answer':text}),schema,validate,300,task='revision')
    s.practice_history.append({'criterion':s.learning_target['key'],'revision':text,'reply':p['reply']})
    return {'reply':p['reply'],'complete':True,'state':s.state(),'practice_revision':s.practice_answers}
