import json
import unittest
from experiments import dab_roadmap_protocol as protocol


class MixedBindingTests(unittest.TestCase):
    def test_binding_survives_compact_views_without_rows(self):
        binding = {'result_type':'human_accepted_stratified_recovery_v1','homogeneous_runtime':False,
                   'human_accepted_mixed':True,'comparability':'confounded','f1_observed_count':8,
                   'regimes':[{'name':'historical','row_count':14,'query_ids':['PRIVATE_TASK'], 'raw_trace':'SECRET'}],
                   'per_query_feedback':['PRIVATE_TASK']}
        result = {'summary':{'query_count':17},'evaluation_binding':binding}
        view = protocol.visible_result(result)
        self.assertFalse(view['evaluation_binding']['homogeneous_runtime'])
        self.assertEqual(view['evaluation_binding']['regimes'][0]['row_count'],14)
        self.assertNotIn('PRIVATE_TASK',json.dumps(view))
        self.assertNotIn('SECRET',json.dumps(view))
        record = {'node_id':'gen4','generation':4,'evaluation_binding':binding}
        self.assertEqual(protocol.compact_graph_node(record)['evaluation_binding'],view['evaluation_binding'])


if __name__ == '__main__': unittest.main()
