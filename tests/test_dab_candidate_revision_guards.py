"""Independent failed-readmission seed guards; no model or benchmark access."""
import copy
from pathlib import Path
import tempfile
import unittest
from experiments import dab_roadmap_protocol as p
from experiments.run_dab_candidate_revision import validate_seed_failure, validate_active_seed_ref

class RevisionSeedGuards(unittest.TestCase):
    def test_bound_ready_marker_with_failed_independent_audit_is_valid(self):
        with tempfile.TemporaryDirectory() as temporary:
            revision = Path(temporary)
            checks = {'passed': False, 'checks': [{'passed': False}], 'source_tree_sha256': 'source',
                      'model_calls': 0, 'database_calls': 0}
            check_path = revision / 'independent.json'
            p.write_json(check_path, checks)
            completion = {'status': 'candidate_revision_ready_for_independent_readmission_audit',
                          'source_tree_sha256': 'source', 'patch_sha256': 'patch', 'formal_evaluation_run': False}
            p.write_json(revision / 'repair_completion.json', completion)
            audit = {'status': 'audited_candidate_revision_runtime_failure', 'seed_source_sha256': 'source',
                     'seed_patch_sha256': 'patch', 'original_bindings_verified': True,
                     'formal_evaluation_run': False, 'independent_readmission_passed': False,
                     'independent_runtime_preflight': str(check_path),
                     'independent_runtime_preflight_sha256': p.sha256_file(check_path),
                     'previous_test_assertions_and_bodies_preserved': True}
            path = revision / 'audit.json'
            p.write_json(path, audit)
            self.assertEqual(validate_seed_failure(revision, path, 'source', 'patch'), audit)
            for key, bad in [('seed_source_sha256', 'changed'), ('seed_patch_sha256', 'changed'),
                             ('original_bindings_verified', False), ('formal_evaluation_run', True),
                             ('independent_readmission_passed', True),
                             ('previous_test_assertions_and_bodies_preserved', False),
                             ('independent_runtime_preflight_sha256', 'changed')]:
                damaged = copy.deepcopy(audit)
                damaged[key] = bad
                p.write_json(path, damaged)
                with self.subTest(field=key), self.assertRaises(AssertionError):
                    validate_seed_failure(revision, path, 'source', 'patch')
            p.write_json(path, audit)
            for key, bad in [('passed', True), ('checks', [{'passed': True}]), ('model_calls', 1),
                             ('database_calls', 1), ('source_tree_sha256', 'changed')]:
                damaged = copy.deepcopy(checks)
                damaged[key] = bad
                p.write_json(check_path, damaged)
                bound = {**audit, 'independent_runtime_preflight_sha256': p.sha256_file(check_path)}
                p.write_json(path, bound)
                with self.subTest(check=key), self.assertRaises(AssertionError):
                    validate_seed_failure(revision, path, 'source', 'patch')

    def test_unexpected_completion_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            revision = Path(temporary)
            audit = {'status': 'audited_candidate_revision_runtime_failure', 'seed_source_sha256': 'source',
                     'seed_patch_sha256': 'patch', 'original_bindings_verified': True, 'formal_evaluation_run': False}
            path = revision / 'audit.json'
            p.write_json(path, audit)
            p.write_json(revision / 'repair_completion.json', {'status': 'evaluated'})
            with self.assertRaises(AssertionError):
                validate_seed_failure(revision, path, 'source', 'patch')
            p.write_json(revision / 'repair_completion.json', {'status': 'versioned_repair_failed_needs_audit'})
            self.assertEqual(validate_seed_failure(revision, path, 'source', 'patch'), audit)

class ReadmittedSeedGuards(unittest.TestCase):
    def test_active_readmitted_seed_requires_exact_audited_chain(self):
        with tempfile.TemporaryDirectory() as temporary:
            revision = Path(temporary) / 'repair_006'; revision.mkdir()
            original = Path(temporary) / 'original.json'; p.write_json(original, {'retained':True})
            previous = {'original_candidate_ref':str(original),'intent_sha256':'intent','materialization_parent_sha256':'base'}
            completion = {'source_tree_sha256':'source','patch_sha256':'patch'}
            p.write_json(revision/'repair_completion.json', completion)
            audit = {'status':'audited_candidate_revision_ready_for_readmission','independent_readmission_passed':True,
                     'formal_evaluation_run':False,'source_tree_sha256':'source','patch_sha256':'patch'}
            audit_path=revision/'completion_audit.json';p.write_json(audit_path,audit)
            ref = {'generation':6,'revision':revision.name,'repo':str(revision/'repo'),'workspace':str(revision),
                   'original_ref':str(original),'original_ref_sha256':p.sha256_file(original),
                   'source_tree_sha256':'source','patch_sha256':'patch','sealed_intent_sha256':'intent',
                   'materialization_parent_sha256':'base','completion_audit':str(audit_path),
                   'completion_audit_sha256':p.sha256_file(audit_path)}
            ref_path=revision/'candidate_ref.json';p.write_json(ref_path,ref)
            validate_active_seed_ref(revision,previous,ref_path,6)
            cases=[('generation',7),('revision','repair_other'),('repo',str(revision/'other')),
                   ('workspace',str(revision/'other')),('original_ref',str(ref_path)),
                   ('original_ref_sha256','other'),('source_tree_sha256','other'),('patch_sha256','other'),
                   ('sealed_intent_sha256','other'),('materialization_parent_sha256','other'),
                   ('completion_audit',str(revision/'wrong.json')),('completion_audit_sha256','other')]
            for key,value in cases:
                damaged={**ref,key:value};p.write_json(ref_path,damaged)
                with self.subTest(field=key), self.assertRaises(AssertionError):
                    validate_active_seed_ref(revision,previous,ref_path,6)
            p.write_json(ref_path,ref)
            with self.assertRaises(AssertionError): validate_active_seed_ref(revision,previous,revision/'other_ref.json',6)
            damaged={**audit,'independent_readmission_passed':False};p.write_json(audit_path,damaged)
            p.write_json(ref_path,{**ref,'completion_audit_sha256':p.sha256_file(audit_path)})
            with self.assertRaises(AssertionError): validate_active_seed_ref(revision,previous,ref_path,6)

if __name__ == '__main__':
    unittest.main()
