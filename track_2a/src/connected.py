"""Bounded German conversational controller. Bank purposes remain code-owned."""
import re
import interview_controller as c
import hybrid as h

def pending(s):return s.plan[s.index+1:]
def choose(s,text,a):
    tail=pending(s);skipped=[]
    answered_history=[]
    for index,turn in enumerate(s.transcript):
        if turn['role']=='assistant' and index+1<len(s.transcript) and s.transcript[index+1]['role']=='user':answered_history.append(turn)
    for question in tail:
        if c.question_repeated(c.question_text(question,'de'),answered_history,'de'):
            s.question_status[question['id']]={'status':'already_asked','answer':s.answers};skipped.append(question['id'])
    for item in a.get('covered_questions',[]):
        q=next((q for q in tail if q['id']==item['question_id']),None)
        if q and q['id'] not in skipped and q['flow_stage'] not in ('candidate_questions','closing') and item['confidence']=='certain' and len(item['quote'].split())>=8:
            s.question_status[q['id']]={'status':'covered','quote':item['quote'],'answer':s.answers};skipped.append(q['id'])
    tail=[q for q in tail if q['id'] not in skipped]
    if not tail:return None,'All planned questions addressed',skipped
    # Never skip past candidate questions/closing; select only from the preceding interview block.
    block=[]
    for q in tail:
        if q['flow_stage'] in ('candidate_questions','closing'):break
        block.append(q)
    current=s.plan[s.index];related=a.get('related_question_id','')
    trial=bool(re.search(r'schnupper|praktikum',text,re.I))
    selected=next((q for q in block if current['subtopic']=='group_task' and q['subtopic']=='group_task_reflection'),None)
    if not selected:selected=next((q for q in block if trial and q['subtopic'] in ('trial_history','trial_apprenticeship')),None)
    reason='Continue the trial-placement topic introduced by the candidate' if selected else ''
    if not selected:
        selected=next((q for q in block if q['subtopic']==current['subtopic'] and q['type']!='smalltalk'),None)
        if selected:reason='Keep questions on the current topic together'
    if not selected and s.topic_run<3:
        selected=next((q for q in block if q['id']==related),None)
        if selected:reason='Continue a relevant topic identified in the current answer'
    if not selected:
        selected=tail[0];reason='Move to the next remaining planned topic'
    # The prefix preserves asked IDs; the suffix can be reordered without breaking API/index semantics.
    s.plan=s.plan[:s.index+1]+[selected]+[q for q in tail if q['id']!=selected['id']]
    return selected,reason,skipped

def speaker(s,text,q,nxt,a,action,reason):
    allowed=c.approved_question_variants(nxt,'de') if nxt else []
    schema=h.obj({'reaction':h.STR,'question':{'type':'string','enum':allowed} if action=='advance' else h.STR,'evidence_quote':{'type':'string','enum':['']+h.parts(text)}})
    data={'action':action,'selection_reason':reason,'current_question':c.answered_question_context(s.transcript,len(s.transcript)-1 if s.transcript and s.transcript[-1]['role']=='user' else len(s.transcript),q,'de'),
          'selected_question':c.question_context(nxt,'de') if nxt else None,'missing_detail':a['missing_information'],
          'explicit_concern':a.get('concern_quote',''),'current_candidate_answer':text,'allowed_questions':allowed if action=='advance' else [],'recent_questions':c.asked_question_texts(s.transcript)[-3:]}
    def validate(p):
        if not all(isinstance(p[k],str) for k in schema['required']):raise ValueError('Invalid connected response')
        reaction=p['reaction'];question=p['question'];quote=p['evidence_quote']
        if len(reaction.split())>22:raise ValueError('Reaction too long')
        if action=='advance' and question not in allowed:raise ValueError('Question does not implement selected purpose')
        if action=='clarify' and (len(question.split())>35 or question.count('?')!=1):raise ValueError('One short clarification required')
        if '?' in reaction or re.search(r'(^|[.!]\s+)(Erzähl|Nenne|Beschreib|Kannst|Wie |Was |Welche |Warum )',reaction) or re.search(r'\bdanke\b|\bzeig(t|st|en)\b|beeindruck|das passt|gut gemacht|antwort beschreibt|kontext des interviews',reaction,re.I):raise ValueError('Generic evaluation/meta response')
        if reaction and (not quote or quote not in text):raise ValueError('Reaction needs current literal evidence')
        if re.search(r'\b(Sie|Ihre|Ihnen)\b',reaction):raise ValueError('Use du')
        if c.question_repeated(question,s.transcript,'de'):raise ValueError('Repeated question')
        if action=='clarify' and any(question in c.approved_question_variants(item,'de') for item in s.plan):raise ValueError('Clarification duplicates planned main purpose')
    try:
        p=s.call(h.messages('connected_speaker',data),schema,validate,550,task='speaker',reserve=2)
        reaction=p['reaction'];question=p['question']
        if reaction and h.normal(reaction) in [h.normal(x) for x in s.speaker_reactions[-3:]]:reaction=''
        s.speaker_reactions.append(reaction);return h.join_reply(reaction,question),p['evidence_quote'],False,question
    except (ValueError,KeyError,TypeError) as e:
        s.validation_warnings.append({'action':'connected_speaker_fallback','reason':str(e)})
        question=c.question_text(nxt,'de') if nxt else 'Was möchtest du dazu noch ergänzen?'
        if c.question_repeated(question,s.transcript,'de'):raise ValueError('Selected purpose has already been asked; choose another question')
        return question,'',True,question

def answer(s,text,recap=False):
    if s.complete:raise ValueError('Session is complete.')
    if text:
        if not isinstance(text,str) or not text.strip() or len(text)>4000:raise ValueError('Invalid answer.')
        text=text.strip();s.record_answer(text)
    elif not recap:raise ValueError('An answer is required.')
    if recap:return h.finish(s)
    q=s.plan[s.index];a=h.analyse(s,text,q)
    s.question_status[q['id']]={'status':a.get('answer_status','answered'),'quote':text,'answer':s.answers}
    nxt,reason,skipped=choose(s,text,a);action='advance';reply='';evidence='';fallback=False;actual_spoken=''
    can_clarify=bool(nxt and not s.current_followups and s.followup_count<3 and q['flow_stage'] not in ('candidate_questions','closing') and q['type']!='smalltalk')
    if a['support_quote']:
        action='support';ack=('Wir können uns Zeit nehmen. Hier musst du nichts beweisen.' if s.support_offered else 'Absagen können weh tun. Sie sagen nicht, was du als Person wert bist. Sprich mit einer vertrauten erwachsenen Person oder der Berufsberatung darüber. Hier darfst du in Ruhe üben.')
        s.support_offered=True
        if a['requests']:ack+=' '+h.company_reply(s,a['requests'])
        reply=h.join_reply(ack,('Wenn du weiterüben möchtest: '+c.question_text(nxt,'de')) if nxt else '')
    elif a['requests']:
        action='answer_company';reply=h.join_reply(h.company_reply(s,a['requests']),c.question_text(nxt,'de') if nxt else '')
    elif nxt:
        action='clarify' if can_clarify and a['missing_information'] else 'advance'
        reply,evidence,fallback,actual_spoken=speaker(s,text,q,nxt,a,action,reason)
        if fallback:action='advance'
    else:reply='Danke für das Gespräch.'
    s.turn_decisions.append({'answer':s.answers,'question_id':q['id'],'action':action,'selected_question_id':nxt['id'] if nxt else None,'selection_reason':reason,'skipped_question_ids':skipped,'reaction_evidence':evidence,'analysis_index':len(s.answer_analyses)-1})
    if action=='clarify':s.current_followups+=1;s.followup_count+=1
    elif nxt:
        s.index+=1;s.current_followups=0;s.main_question_count+=1;s.set_question(nxt)
    s.topic_run=s.topic_run+1 if nxt and nxt['subtopic']==q['subtopic'] else 0
    topic=q['flow_stage']+':'+q['subtopic']
    if topic not in s.covered_topics:s.covered_topics.append(topic)
    s.conversation_state='clarification' if action=='clarify' else 'interview'
    actual_next=c.question_text(nxt,'de') if nxt else ''
    if action in ('advance','clarify') and nxt:actual_next=actual_spoken
    if reply:s.transcript.append({'role':'assistant','content':reply,'question_id':s.plan[s.index]['id'],'stage':s.current_stage,'actual_question':actual_next,'followup':action=='clarify','action':action})
    if not nxt or s.answers>=18:s.roleplay_finished=True;return h.finish(s)
    return {'reply':reply,'hint':'','complete':False,'can_continue':True,'suggest_recap':False,'state':s.state()}
