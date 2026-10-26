import copy
import unittest
from experiments.admit_dab_candidate_revision import check_evidence

class RevisionAdmissionGuards(unittest.TestCase):
    def values(self):
        return [
            {'stage':'candidate_admitted','next_generation':6,'active_candidate_ref':'original'},
            {'human_authorized':True,'same_sealed_intent':True,'generation':6,'original_candidate_ref':'original','intent_sha256':'intent','materialization_parent_sha256':'base','graph_head_sha256':'head'},
            {'status':'candidate_revision_ready_for_independent_readmission_audit','generation':6,'original_candidate_ref':'original','original_preserved':True,'formal_evaluation_run':False,'source_tree_sha256':'source','patch_sha256':'patch','intent_sha256':'intent','runtime_preflight_passed':True},
            {'intent_canonical_sha256':'intent','parent_source_sha256':'base'},
            {'status':'source_preflight_passed','claim_to_source_valid':True,'implementation_files':['experiments/a.py'],'changed_files':['experiments/a.py'],'failures':[],'forbidden_files':[],'checks':[{'passed':True}],'patch_sha256':'patch'},
            {'status':'audited_candidate_revision_ready_for_readmission','generation':6,'independent_readmission_passed':True,'original_bindings_verified':True,'previous_test_assertions_and_bodies_preserved':True,'report_claims_reviewed':True,'formal_evaluation_run':False,'source_tree_sha256':'source','patch_sha256':'patch','intent_sha256':'intent','materialization_parent_sha256':'base','graph_head_sha256':'head','independent_runtime_checks_failed':0,'independent_runtime_checks_passed':1},
            {'source_tree_sha256':'source','passed':True,'checks':[{'passed':True}],'model_calls':0,'database_calls':0},
            {'canonical_json_sha256':'intent','code_parent_hash':'base'},
            {'ok':True,'head_record_sha256':'head'}, 'source', 'patch', 6]
    def test_genuine_bindings_accepted_without_mutation(self):
        values = self.values(); before = copy.deepcopy(values)
        check_evidence(*values)
        self.assertEqual(values, before)
    def test_each_unbound_or_failed_state_rejected(self):
        cases = [(0,'stage','result_recorded'),(0,'next_generation',7),(0,'active_candidate_ref','other'),
            (1,'human_authorized',False),(1,'same_sealed_intent',False),(1,'generation',7),
            (2,'status','versioned_repair_failed_needs_audit'),(2,'original_preserved',False),(2,'formal_evaluation_run',True),
            (2,'source_tree_sha256','other'),(2,'patch_sha256','other'),(2,'intent_sha256','other'),
            (3,'parent_source_sha256','other'),(3,'intent_canonical_sha256','other'),
            (4,'claim_to_source_valid',False),(4,'implementation_files',[]),(4,'failures',['error']),
            (4,'forbidden_files',['outside']),(4,'checks',[{'passed':False}]),
            (5,'independent_readmission_passed',False),(5,'previous_test_assertions_and_bodies_preserved',False),
            (5,'original_bindings_verified',False),(5,'report_claims_reviewed',False),(5,'formal_evaluation_run',True),
            (5,'independent_runtime_checks_failed',1),(5,'independent_runtime_checks_passed',2),
            (6,'passed',False),(6,'checks',[{'passed':False}]),(6,'source_tree_sha256','other'),
            (6,'model_calls',1),(6,'database_calls',1),(8,'ok',False),(8,'head_record_sha256','other')]
        for index,key,value in cases:
            with self.subTest(index=index,key=key):
                values=self.values();values[index][key]=value
                with self.assertRaises(ValueError): check_evidence(*values)

if __name__ == '__main__': unittest.main()
