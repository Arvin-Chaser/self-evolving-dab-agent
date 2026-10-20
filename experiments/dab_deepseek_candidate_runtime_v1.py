"""Fresh candidate-bound native GPT infrastructure, no algorithm substitution.

Optional inherited Gen8 gate remains typed/validated. Future Meta-declared state
is explicitly typed and losslessly persisted; unsupported types fail closed.
"""
import copy,json,os,time
from pathlib import Path
from adapters.deepseek_client_v1 import MODEL,ENDPOINT
from adapters.deepseek_wire_client_v1 import install_native_transport
from experiments import dab_runtime_repair_v1 as base
from experiments import dab_gen008_gpt_runtime_v1 as inherited
from experiments.dab_deepseek_isolation_v1 import prepare_isolation,dispatch_once
POLICY='deepseek_candidate_native_high_isolated_lossless_once_v1'
CONTRACT=[]
def validate_json(value):
    if value is None or type(value) in (str,bool,int,float):return
    if type(value) is list:
        for x in value:validate_json(x)
        return
    if type(value) is dict and all(type(k) is str for k in value):
        for x in value.values():validate_json(x)
        return
    raise base.UnsafeResume('Unsupported non-JSON candidate state; no silent coercion')
def validate_contract(value):
    if not isinstance(value,dict) or set(value)!={'persistent_fields','stateless'} or type(value['stateless']) is not bool:raise base.UnsafeResume('Missing explicit candidate state contract')
    fields=value['persistent_fields']
    if not isinstance(fields,list) or len(fields)>100:raise base.UnsafeResume('Invalid bounded persistent fields')
    names=[]
    for field in fields:
        if not isinstance(field,dict) or set(field)!={'name','type'} or not isinstance(field['name'],str) or not field['name'].isidentifier() or field['type'] not in ('json','string_set'):raise base.UnsafeResume('Unsupported candidate state field')
        if field['name'] in ('client','tools','messages','journal','turn_checkpoint_recovery','_gen9_candidate_state'):raise base.UnsafeResume('Reserved field cannot override typed native state')
        names.append(field['name'])
    if len(names)!=len(set(names)) or value['stateless'] is not (len(fields)==0):raise base.UnsafeResume('Ambiguous state contract')
    return fields
def pack(agent):
    values={}
    for field in CONTRACT:
        name=field['name']
        if not hasattr(agent,name):raise base.UnsafeResume('Actual candidate field missing: '+name)
        value=copy.deepcopy(getattr(agent,name))
        if field['type']=='string_set':
            if not isinstance(value,set) or any(not isinstance(x,str) for x in value):raise base.UnsafeResume('Invalid candidate signature set')
            value=sorted(value)
        else:
            # JSON supports non-finite values here only because the outer
            # durable wire uses the audited lossless typed codec.
            validate_json(value)
        values[name]=value
    return values
def restore_fields(agent,values):
    if not isinstance(values,dict) or set(values)!={f['name'] for f in CONTRACT}:raise base.UnsafeResume('Candidate state key mismatch')
    for field in CONTRACT:
        value=values[field['name']]
        if field['type']=='string_set':
            if not isinstance(value,list) or any(not isinstance(x,str) for x in value) or value!=sorted(set(value)):raise base.UnsafeResume('Noncanonical candidate signature set')
            value=set(value)
        else:validate_json(value)
        setattr(agent,field['name'],copy.deepcopy(value))
class CandidateJournal(inherited.NativeJournal):
    def accept(self,message):
        self.pending=message.model_dump() if hasattr(message,'model_dump') else message.to_dict()
        self.cursor=0
        if self.pending.get('tool_calls') is not None:
            self.agent.messages.append(copy.deepcopy({k:self.pending[k] for k in ('role','content','tool_calls','reasoning_content') if k in self.pending}))
        self.save()
    def dispatch(self):
        if self.pending.get('tool_calls') is not None:return base.Journal.dispatch(self)
        self.agent.messages.append(copy.deepcopy({k:self.pending[k] for k in ('role','content','reasoning_content') if k in self.pending}))
        self.agent._handle_content(self.pending.get('content'))
        self.pending=None;self.cursor=0;self.save()
    def save(self,recovery=None):
        self.agent._gen9_candidate_state=pack(self.agent)
        return super().save(recovery)
    def restore(self,payload):
        values=payload['state'].get('_gen9_candidate_state')
        probe=copy.copy(self.agent);restore_fields(probe,values)
        super().restore(payload);restore_fields(self.agent,values)
def install(module,args):
    global CONTRACT
    if args.deployment_name!=MODEL or args.openai_compatible_base_url!=ENDPOINT or args.client_max_retries!=0 or args.llm_retries!=1 or any(os.environ.get(k) for k in ('DAB_REPAIR_RESUME','DAB_DEEPSEEK_SINGLE_TRIAL','DAB_SCHOOL_REMAINING8_TRIAL')):raise RuntimeError('Fresh DeepSeek candidate binding/no-replay mismatch')
    binding=json.loads((Path(__file__).resolve().parents[1]/'candidate_runtime_binding.json').read_text(encoding='utf-8'))
    CONTRACT=validate_contract(binding['runtime_state_contract'])
    prepare_isolation(module,args)
    base.POLICY=POLICY
    base.ADMITTED_SOURCE_SHA256=binding['admitted_source_sha256'];base.ADMITTED_PATCH_SHA256=binding['admitted_patch_sha256'];base.SEALED_INTENT_SHA256=binding['sealed_intent_sha256']
    base.STATE_FIELDS=tuple(base.STATE_FIELDS)+('_gen8_checkpoint_state','_gen9_candidate_state')
    base.Journal=CandidateJournal;base.install(module,args);parent=module.DataAgent
    class CandidateDeepSeekDataAgent(parent):
        def __init__(self,**kw):
            super().__init__(**kw);inherited.serialize_gate(self,required=False);pack(self);install_native_transport(self.client,self.root_dir)
        def call_llm(self):
            self.journal.save();request={'model':self.deployment_name,'messages':copy.deepcopy(self.messages),'tools':[t.get_spec() for t in self.tools.values()],'timeout':args.llm_timeout};started=time.monotonic()
            response=dispatch_once(lambda:self.client.chat.completions.create(**request),self.journal.save)
            self.llm_call_count+=1;self.terminate_reason=None
            with self.llm_log_path.open('a',encoding='utf-8') as stream:stream.write(json.dumps({'timestamp':time.time(),'duration':time.monotonic()-started,'model':MODEL,'response':response.to_dict(),'messages':self.messages,'repair_policy':POLICY})+'\n')
            self.journal.accept(response.choices[0].message);return response.choices[0].message
        def to_dict(self):
            value=super().to_dict();value['candidate_runtime_state']=pack(self);value['gen8_duplicate_gate_state']=inherited.serialize_gate(self,required=False);value['native_deepseek_history']={'policy':POLICY,'reasoning_effort':'high','native_reasoning_content_preserved':True,'automatic_request_replay':False};return value
    module.DataAgent=CandidateDeepSeekDataAgent
