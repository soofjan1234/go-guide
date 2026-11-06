"""验证投递筛选、去重与发送不确定时的恢复行为。"""

import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import Mock, patch

import boss_apply as app


def job(**updates):
    """构造完整岗位，不依赖真实聊天或网络。"""
    value = dict(title="Go开发工程师", company="示例公司", hr="李女士", salary="18-25K",
                 location="深圳·南山", experience="3-5年", degree="本科",
                 jd="负责 Go 服务开发，使用 MySQL、Redis，完成接口设计、性能优化与线上维护。",
                 jd_complete=True, contacted=False)
    value.update(updates)
    return value


class ScreeningTests(unittest.TestCase):
    """筛选只依据岗位事实，含糊条件进入待核。"""

    def test_matching_backend_is_ready(self):
        self.assertEqual(app.evaluate_job(job(), app.Criteria())["status"], "ready")

    def test_explicit_outsourcing_is_skipped(self):
        self.assertEqual(app.evaluate_job(job(title="Go外包工程师"), app.Criteria())["status"], "skipped")

    def test_negative_outsourcing_and_company_name_do_not_exclude(self):
        value = job(company="外包服务科技", jd="非外包，不驻场；Go、MySQL 后端开发，无外包经历要求。")
        self.assertEqual(app.evaluate_job(value, app.Criteria())["status"], "ready")

    def test_non_outsourcing_title_does_not_exclude(self):
        self.assertEqual(app.evaluate_job(job(title="Go开发（非外包）"), app.Criteria())["status"], "ready")

    def test_explicit_onsite_is_skipped(self):
        self.assertEqual(app.evaluate_job(job(jd="Go开发，需要长期驻场客户公司"), app.Criteria())["status"], "skipped")

    def test_overlapping_salary_is_ready(self):
        for salary in ("20-30K·13薪", "11-20K", "12-15K", "25-30K"):
            with self.subTest(salary=salary):
                self.assertEqual(app.evaluate_job(job(salary=salary), app.Criteria())["status"], "ready")

    def test_salary_outside_target_is_skipped(self):
        self.assertEqual(app.evaluate_job(job(salary="8-12K"), app.Criteria())["status"], "skipped")

    def test_missing_salary_needs_review(self):
        self.assertEqual(app.evaluate_job(job(salary="面议"), app.Criteria())["status"], "review")

    def test_other_city_is_skipped(self):
        self.assertEqual(app.evaluate_job(job(location="杭州"), app.Criteria())["status"], "skipped")

    def test_incomplete_description_never_ready(self):
        self.assertEqual(app.evaluate_job(job(jd_complete=False), app.Criteria())["status"], "review")

    def test_bonus_k8s_does_not_exclude(self):
        self.assertEqual(app.evaluate_job(job(jd="Go开发；熟悉MySQL，K8s生产经验优先"), app.Criteria())["status"], "ready")

    def test_hard_missing_experience_needs_review(self):
        self.assertEqual(app.evaluate_job(job(jd="Go开发，必须有三年以上生产K8s集群运维经验"), app.Criteria())["status"], "review")

    def test_non_go_backend_is_skipped(self):
        self.assertEqual(app.evaluate_job(job(title="Java开发", jd="Java Spring后端"), app.Criteria())["status"], "skipped")

    def test_agent_titles_are_filtered_before_reading_jd(self):
        for title in ('AI Agent研发工程师','AIAgent研发工程师','全栈agent工程师','智能体开发工程师','Agentic AI工程师'):
            with self.subTest(title=title):
                self.assertEqual(app.prefilter_job(job(title=title),app.Criteria())['status'],'skipped')

    def test_agent_core_duties_are_filtered_even_with_generic_go_title(self):
        for jd in ('岗位职责：负责 AI Agent 的设计、开发和评测；使用 Go。',
                   '岗位职责\n负责 Go 后端及多智能体编排系统建设。',
                   '任职要求：熟练掌握 Go，必须具有 LangGraph Agent 开发经验。'):
            with self.subTest(jd=jd):
                self.assertEqual(app.evaluate_job(job(jd=jd),app.Criteria())['status'],'skipped')

    def test_agent_integration_duties_are_filtered_without_development_verbs(self):
        for jd in ('岗位职责\n使用 Go 和 AI Agent 及工具链，将智能问答能力接入业务系统。',
                   '岗位职责\nGo 服务将数据基础能力稳定接入 Agent、知识库和业务应用。'):
            with self.subTest(jd=jd):
                self.assertEqual(app.evaluate_job(job(jd=jd),app.Criteria())['status'],'skipped')

    def test_coding_tool_clause_does_not_hide_agent_development_duties(self):
        value=job(jd='负责 Go Agent 系统开发，使用 AI 编程工具提高研发效率。')
        self.assertEqual(app.evaluate_job(value,app.Criteria())['status'],'skipped')

    def test_agent_keywords_are_excluded_even_in_bonus_or_tool_clauses(self):
        for jd in ('负责 Go 后端开发。\n加分项\n有 AI Agent 开发经验者优先。',
                   '负责 Go API 服务；使用 AI Agent 编程工具提升开发效率。',
                   '负责 Go 后台及终端 Agent 通信、设备数据采集。'):
            with self.subTest(jd=jd):
                self.assertEqual(app.evaluate_job(job(jd=jd),app.Criteria())['status'],'skipped')

    def test_bonus_heading_cannot_hide_later_agent_mentions(self):
        jd='负责 Go 后端开发。\n加分项\n有容器经验。\n岗位亮点\n直接参与行业大模型智能体的搭建。'
        self.assertEqual(app.evaluate_job(job(jd=jd),app.Criteria())['status'],'skipped')


class RecoveryTests(unittest.TestCase):
    """跨重启发送记录须阻止二次触发。"""

    def test_journal_started_attempt_blocks_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal = app.Journal(Path(tmp))
            journal.record(job(), "sending", "提交前已落盘")
            self.assertTrue(app.Journal(Path(tmp)).contains(job()))

    def test_company_different_job_not_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal = app.Journal(Path(tmp))
            journal.record(job(), "sent", "已见本人消息")
            self.assertFalse(journal.contains(job(title="Go平台工程师")))

    def test_history_with_missing_hr_still_blocks_same_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"results.json"
            path.write_text(json.dumps([dict(company="示例公司", list_job_title="Go开发工程师")]), encoding="utf-8")
            history = app.History([path])
            self.assertTrue(history.contains(job()))
            self.assertFalse(history.contains(job(title="Go平台工程师")))

    def test_same_company_role_with_another_hr_is_still_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal=app.Journal(Path(tmp))
            journal.record(job(),'contacted','已核对')
            self.assertTrue(journal.contains(job(hr='另一位招聘人')))
            path=Path(tmp)/'history.json'
            path.write_text(json.dumps([job()]),encoding='utf-8')
            self.assertTrue(app.History([path]).contains(job(hr='另一位招聘人')))


class OptimizationTests(unittest.TestCase):
    """验证列表预筛、JD 缓存和批次中断续跑，不连接真实手机。"""

    def test_list_filter_only_rejects_explicit_facts(self):
        for updates in ({'salary': '8-12K'}, {'location': '杭州'}, {'title': 'Go外包开发'}):
            with self.subTest(updates=updates):
                self.assertEqual(app.prefilter_job(job(**updates), app.Criteria())['status'], 'skipped')
        for updates in ({'title': '服务器工程师'}, {'salary': '面议'}, {'location': ''},
                        {'title': 'Go开发（非外包）'}):
            with self.subTest(updates=updates):
                self.assertEqual(app.prefilter_job(job(**updates), app.Criteria())['status'], 'candidate')

    def test_unchanged_detail_reuses_complete_jd_without_ocr(self):
        snap = contact_page()
        for rid, text in [('tv_job_salary', '18-25K'), ('tv_required_location', '深圳·南山'),
                          ('tv_required_work_exp', '3-5年'), ('tv_required_degree', '本科'),
                          ('tv_description', '负责 Go 服务开发 查看更多')]:
            ET.SubElement(snap.root[0], 'node', {'resource-id': 'id/'+rid, 'text': text})
        snap = app.Snapshot(ET.tostring(snap.root, encoding='unicode'))
        device = Mock()
        device.tap.return_value = snap
        cached = job(jd_preview='负责 Go 服务开发 查看更多')
        value, _ = app.Device.read_job(device, job(node=object()), snap, cached=cached)
        self.assertEqual(value['jd'], cached['jd'])
        self.assertTrue(value['cache_hit'])
        device.expand_jd.assert_not_called()

    def test_changed_preview_invalidates_jd_cache(self):
        snap = contact_page()
        for rid, text in [('tv_job_salary', '18-25K'), ('tv_required_location', '深圳·南山'),
                          ('tv_required_work_exp', '3-5年'), ('tv_required_degree', '本科'),
                          ('tv_description', 'Go开发，新增任职要求')]:
            ET.SubElement(snap.root[0], 'node', {'resource-id': 'id/'+rid, 'text': text})
        snap = app.Snapshot(ET.tostring(snap.root, encoding='unicode'))
        device = Mock()
        device.tap.return_value = snap
        value, _ = app.Device.read_job(device, job(node=object()), snap,
                                     cached=job(jd_preview='旧的折叠正文 查看更多'))
        self.assertEqual(value['jd'], 'Go开发，新增任职要求')
        self.assertFalse(value['cache_hit'])

    def test_resume_counts_journal_success_and_contacts_only_remaining_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            first, second = job(), job(title='Go平台工程师')
            report = dict(version=3, started_at=app.now(), serial='phone', account='one',
                          criteria=app.asdict(app.Criteria()), target=2, contacted=0, complete=False,
                          records=[dict(first, status='ready', attempted=True)], history_paths=[], timings={})
            app.write_json(out/'results.json', report)
            journal = app.Journal(out)
            journal.record(first, 'contacting', '已点击')
            journal.record(first, 'contacted', '聊天证据已核对', 'proof.xml')
            snap = Mock()
            snap.state.return_value = 'search_results'
            snap.rows.return_value = [first, second]
            device = Mock(serial='phone')
            device.salary_filter.return_value = snap
            device.return_to_results.return_value = snap
            device.read_job.side_effect = lambda row, current: (dict(second), contact_page())

            def contact(value, log):
                """模拟第二个岗位建立沟通，第一条由日志恢复。"""
                log.record(value, 'contacted', '已核对', 'proof2.xml')
                return contact_page('chat')

            device.contact_job.side_effect = contact
            app.run_jobs(device, app.Criteria(), app.History(), journal, 2, 1, 'one', out)
            saved = json.loads((out/'results.json').read_text(encoding='utf-8'))
            self.assertEqual(saved['contacted'], 2)
            self.assertTrue(saved['complete'])
            self.assertEqual(device.contact_job.call_count, 1)
            self.assertEqual(device.read_job.call_args.args[0]['title'], second['title'])

    def test_unknown_attempt_blocks_resume_before_device_actions(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            app.write_json(out/'results.json', dict(version=3, started_at=app.now(), serial='phone',
                account='one', criteria=app.asdict(app.Criteria()), target=1, contacted=0,
                complete=False, records=[dict(job(), status='ready', attempted=True)], timings={}))
            journal = app.Journal(out)
            journal.record(job(), 'contacting', '进程在结果核对前退出')
            device = Mock(serial='phone')
            with self.assertRaises(app.StopRun):
                app.run_jobs(device, app.Criteria(), app.History(), journal, 1, 1, 'one', out)
            device.search.assert_not_called()
            device.contact_job.assert_not_called()

    def test_completed_batch_rerun_never_starts_another_ten(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            app.write_json(out/'results.json', dict(version=3, started_at=app.now(), serial='phone',
                account='one', criteria=app.asdict(app.Criteria()), target=1, contacted=1,
                complete=True, records=[dict(job(), status='contacted')], timings={}))
            device = Mock(serial='phone')
            app.run_jobs(device, app.Criteria(), app.History(), app.Journal(out), 1, 1, 'one', out)
            device.search.assert_not_called()

    def test_expired_navigation_snapshot_is_refreshed(self):
        with tempfile.TemporaryDirectory() as tmp:
            device = app.Device('phone', Path(tmp))
            snap = contact_page()
            snap.captured_at -= 10
            device.capture = Mock(return_value=contact_page())
            device.call = Mock()
            device.scroll(snap=snap)
            self.assertEqual(device.capture.call_args_list[0].args, ('before-scroll',))

    def test_fresh_navigation_does_not_repeat_pre_scroll_dump(self):
        with tempfile.TemporaryDirectory() as tmp:
            device = app.Device('phone', Path(tmp))
            device.capture = Mock(return_value=contact_page())
            device.call = Mock()
            device.scroll(snap=contact_page())
            self.assertEqual(device.capture.call_count, 1)
            self.assertEqual(device.capture.call_args.args, ('after-scroll',))

    def test_contact_button_checks_identity_again_after_fresh_dump(self):
        with tempfile.TemporaryDirectory() as tmp:
            device = app.Device('phone', Path(tmp))
            device.capture = Mock(return_value=contact_page(company='另一家公司'))
            device.call = Mock()
            snap = contact_page()
            with self.assertRaises(app.StopRun):
                device.tap(snap, snap.unique(rid='btn_chat'))
            device.call.assert_not_called()

    def test_clipped_description_does_not_trigger_screenshot_or_ocr(self):
        xml = ('<hierarchy><node package="com.hpbr.bosszhipin" bounds="[0,0][1080,2400]">'
               '<node scrollable="true" bounds="[0,0][1080,2200]">'
               '<node resource-id="id/tv_description" text="Go开发 查看更多" bounds="[60,1200][1020,2200]"/>'
               '</node></node></hierarchy>')
        with tempfile.TemporaryDirectory() as tmp:
            device = app.Device('phone', Path(tmp))
            device.call = Mock()
            snap = app.Snapshot(xml)
            self.assertIs(device.expand_jd(snap), snap)
            device.call.assert_not_called()
            self.assertEqual(device.metrics['ocr_calls'], 0)

    def test_new_batch_archives_report_and_keeps_journal_dedup(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            previous = dict(version=3, batch_id='original', started_at=app.now(), serial='phone',
                account='one', criteria=app.asdict(app.Criteria()), target=1, contacted=1,
                complete=True, records=[dict(job(), status='contacted')], timings={})
            app.write_json(out/'results.json', previous)
            journal = app.Journal(out)
            journal.record(job(), 'contacted', '已核对')
            snap = Mock()
            snap.state.return_value = 'search_results'
            snap.rows.return_value = [job()]
            device = Mock(serial='phone')
            device.salary_filter.return_value = snap
            device.scroll.return_value = snap
            app.run_jobs(device, app.Criteria(), app.History(), journal, 1, 1, 'one', out, new_batch=True)
            self.assertTrue((out/'results-original.json').is_file())
            device.read_job.assert_not_called()
            device.contact_job.assert_not_called()
            saved = json.loads((out/'results.json').read_text(encoding='utf-8'))
            self.assertEqual(saved['contacted'], 0)
            self.assertFalse(saved['complete'])
            self.assertEqual(saved['state'], 'exhausted')

    def test_resume_reuses_cached_jd_and_saved_history_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            history_path = out/'history.json'
            history_path.write_text('[]', encoding='utf-8')
            cached = dict(job(), status='ready', jd_preview='Go开发 查看更多')
            app.write_json(out/'results.json', dict(version=3, started_at=app.now(), serial='phone',
                account='one', criteria=app.asdict(app.Criteria()), target=1, contacted=0, complete=False,
                records=[cached], history_paths=[str(history_path)], timings={}))
            snap = Mock()
            snap.state.return_value = 'search_results'
            snap.rows.return_value = [job()]
            device = Mock(serial='phone')
            device.salary_filter.return_value = snap
            device.return_to_results.return_value = snap
            device.read_job.return_value = (job(cache_hit=True), contact_page())

            def contact(value, log):
                """模拟复用缓存的岗位成功沟通。"""
                log.record(value, 'contacted', '已核对', 'proof.xml')
                return contact_page('chat')

            device.contact_job.side_effect = contact
            app.run_jobs(device, app.Criteria(), app.History(), app.Journal(out), 1, 1, 'one', out)
            self.assertEqual(device.read_job.call_args.kwargs['cached']['jd'], cached['jd'])
            saved = json.loads((out/'results.json').read_text(encoding='utf-8'))
            self.assertEqual(len(saved['records']), 1)
            self.assertEqual(saved['history_paths'], [str(history_path.resolve())])
            self.assertTrue(saved['complete'])

    def test_new_batch_does_not_bypass_an_unconfirmed_click(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            app.write_json(out/'results.json', dict(version=3, started_at=app.now(), serial='phone',
                account='one', criteria=app.asdict(app.Criteria()), target=1, contacted=0,
                complete=False, records=[dict(job(), status='unknown', attempted=True)], timings={}))
            journal = app.Journal(out)
            journal.record(job(), 'unknown', '需要核对实际聊天')
            device = Mock(serial='phone')
            with self.assertRaises(app.StopRun):
                app.run_jobs(device, app.Criteria(), app.History(), journal, 1, 1, 'one', out, new_batch=True)
            device.search.assert_not_called()

    def test_incompatible_resume_conditions_do_not_open_phone(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            app.write_json(out/'results.json', dict(version=3, started_at=app.now(), serial='phone',
                account='one', criteria=app.asdict(app.Criteria()), target=1, contacted=0,
                complete=False, records=[], timings={}))
            device = Mock(serial='phone')
            with self.assertRaises(app.StopRun):
                app.run_jobs(device, app.Criteria(city='杭州'), app.History(), app.Journal(out), 1, 1, 'one', out)
            device.search.assert_not_called()


class FastCaptureTests(unittest.TestCase):
    """覆盖常驻采集的裁剪、页面过渡和只读降级，所有输入均被替换。"""

    def test_clip_negative_and_offscreen_bounds_to_current_viewport(self):
        xml = ('<hierarchy><node package="com.hpbr.bosszhipin" bounds="[0,0][1080,2400]">'
               '<node resource-id="id/top" bounds="[-10,-40][300,100]"/>'
               '<node resource-id="id/btn_chat" bounds="[75,2223][1005,2355]"/>'
               '<node resource-id="id/hidden" bounds="[60,2350][900,2398]"/>'
               '</node></hierarchy>')
        snap = app.Snapshot(xml, viewport=(1080,2320))
        self.assertEqual((snap.width,snap.height),(1080,2320))
        self.assertEqual(snap.bounds(snap.unique(rid='top')),(0,0,300,100))
        self.assertEqual(snap.bounds(snap.unique(rid='btn_chat')),(75,2223,1005,2320))
        self.assertEqual(snap.bounds(snap.unique(rid='hidden')),(0,0,0,0))

    def test_display_viewport_uses_primary_override_not_physical_or_virtual_size(self):
        text=('mBaseDisplayInfo=DisplayInfo{displayId 0, real 1080 x 2400, app 1080 x 2400, rotation 0}\n'
              'mOverrideDisplayInfo=DisplayInfo{displayId 0, real 1080 x 2400, rotation 0, app 1080 x 2320, density 480}\n'
              'mOverrideDisplayInfo=DisplayInfo{displayId 90000, rotation 0, app 1080 x 2400, density 480}')
        self.assertEqual(app.display_viewport(text),(1080,2320,0))
        self.assertEqual(app.display_viewport(text.replace('app 1080 x 2320','app 2320 x 1080').replace('rotation 0','rotation 1')),(2320,1080,1))

    def test_unknown_viewport_is_not_guessed(self):
        with self.assertRaises(app.StopRun):
            app.display_viewport('DisplayInfo{real 1080 x 2400}')

    def test_known_job_footer_remains_readable_after_title_and_jd_are_recycled(self):
        xml=('<hierarchy><node package="com.hpbr.bosszhipin" bounds="[0,0][1080,2320]">'
             '<node resource-id="id/iv_back"/>'
             '<node resource-id="id/tv_job_competitive_title" text="你的竞争力分析"/>'
             '<node resource-id="id/btn_chat" text="立即沟通"/>'
             '</node></hierarchy>')
        snap=app.Snapshot(xml)
        self.assertEqual(snap.state(),'job')
        self.assertTrue(app.UiautomatorDevice.page_ready(snap))

    def test_company_ellipsis_display_does_not_change_identity(self):
        self.assertEqual(app.identity(job(company='示例公司...')),app.identity(job(company='示例公司.....')))
        self.assertNotEqual(app.identity(job(company='示例公司...')),app.identity(job(company='示例公司科技有限公司')))

    def test_known_preference_prompt_is_dismissed_without_adding_expectations(self):
        xml=('<hierarchy><node package="com.hpbr.bosszhipin" bounds="[0,0][1080,2320]">'
             '<node text="你可能感兴趣以下工作"/><node text="添加多个求职期望，更容易找到工作"/>'
             '<node text="立即添加"/></node></hierarchy>')
        prompt=app.Snapshot(xml)
        self.assertEqual(prompt.state(),'preference_prompt')
        with tempfile.TemporaryDirectory() as tmp:
            device=app.Device('phone',Path(tmp))
            device.call=Mock()
            device.capture=Mock(return_value=contact_page())
            device.back(prompt)
            device.call.assert_called_once_with('shell','input','keyevent','4')

    def test_u2_search_sets_whole_text_without_keyboard_events(self):
        xml=('<hierarchy><node package="com.hpbr.bosszhipin" bounds="[0,0][1080,2320]">'
             '<node resource-id="id/et_search" class="android.widget.EditText" text="og" focused="true"/>'
             '<node resource-id="id/tv_search" text="搜索"/></node></hierarchy>')
        before=app.Snapshot(xml)
        after=app.Snapshot(xml.replace('text="og"','text="go"'))
        with tempfile.TemporaryDirectory() as tmp:
            client=Mock()
            device=app.UiautomatorDevice('phone',Path(tmp),client=client)
            device.tap=Mock(return_value=before)
            device.after_action=Mock(return_value=after)
            device.call=Mock()
            result=device.fill_ascii(before,before.unique(rid='et_search'),'go')
            self.assertEqual(result.text('et_search'),'go')
            client.return_value.set_text.assert_called_once_with('go',timeout=1)
            device.call.assert_not_called()

    def test_contact_waits_for_matching_chat_without_repeating_click(self):
        with tempfile.TemporaryDirectory() as tmp:
            device=app.UiautomatorDevice('phone',Path(tmp),client=Mock())
            start=contact_page()
            device.capture=Mock(side_effect=[start,start,contact_page('chat',hr='其他人'),contact_page('chat'),contact_page('chat')])
            device.call=Mock()
            with patch.object(app.time,'sleep'), patch.object(app.time,'perf_counter',side_effect=[0,.3,.4]):
                result=device.tap(start,start.unique(rid='btn_chat'))
            self.assertTrue(app.Device.check_contact(job(),result))
            self.assertEqual(device.call.call_count,1)

    def test_filter_waits_for_animation_bounds_to_stop_changing(self):
        xml=('<hierarchy><node package="com.hpbr.bosszhipin" bounds="[0,0][1080,2320]">'
             '<node resource-id="id/btn_confirm" text="确定"/>'
             '<node resource-id="id/tv_condition_title" text="薪资待遇"/>'
             '<node resource-id="id/keywords_view_text" text="10-20K" bounds="[100,900][300,1000]"/>'
             '</node></hierarchy>')
        moving=app.Snapshot(xml)
        settled=app.Snapshot(xml.replace('[100,900][300,1000]','[100,600][300,700]'))
        with tempfile.TemporaryDirectory() as tmp:
            device=app.UiautomatorDevice('phone',Path(tmp),client=Mock())
            device.capture=Mock(side_effect=[moving,settled,settled])
            with patch.object(app.time,'sleep'),patch.object(app.time,'perf_counter',side_effect=[0,.3,.4]):
                result=device.after_action('after-tap',lambda current:current.state()=='filter')
            self.assertIs(result,settled)

    def test_wait_timeout_never_clicks_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            device=app.UiautomatorDevice('phone',Path(tmp),client=Mock())
            device.page_timeout=0
            start=contact_page()
            device.capture=Mock(return_value=start)
            device.call=Mock()
            with self.assertRaises(app.StopRun):
                device.tap(start,start.unique(rid='btn_chat'))
            self.assertEqual(device.call.call_count,1)

    def test_broken_u2_capture_stops_service_then_falls_back_to_readonly_adb(self):
        with tempfile.TemporaryDirectory() as tmp:
            client=Mock()
            client.dump_hierarchy.side_effect=RuntimeError('service disconnected')
            device=app.UiautomatorDevice('phone',Path(tmp),client=client)
            display=b'mOverrideDisplayInfo=DisplayInfo{displayId 0, rotation 0, app 1080 x 2320, density 480}'
            device.call=Mock(side_effect=[display,b'UI hierchary dumped to: file',ET.tostring(contact_page().root)])
            snap=device.capture('fallback-test')
            self.assertEqual(snap.state(),'job')
            client.stop_uiautomator.assert_called_once()
            self.assertEqual(device.metrics['fallbacks'],1)
            self.assertFalse(any('input' in call.args for call in device.call.call_args_list))


def list_page(experience='3-5年', degree='本科', extra=''):
    """复现列表中没有资源名的经验学历标签，保留卡片的实际分组。"""
    return app.Snapshot('<hierarchy rotation="0"><node package="com.hpbr.bosszhipin" bounds="[0,0][1080,2320]">'
        '<node resource-id="id/tv_search_hint" text="go"/>'
        '<node resource-id="id/tv_tab_label" text="筛选"/>'
        '<node bounds="[0,500][1080,1100]">'
        '<node resource-id="id/tv_position_name" text="Go开发工程师" bounds="[50,550][800,650]"/>'
        '<node resource-id="id/tv_company_name" text="示例公司"/>'
        '<node resource-id="id/tv_employer" text="李女士 · 人事"/>'
        '<node resource-id="id/tv_salary_statue" text="18-25K"/>'
        '<node resource-id="id/tv_distance" text="深圳·南山"/>'
        f'<node text="{experience}"/><node text="{degree}"/>{extra}'
        '</node></node></hierarchy>')


class FasterPollingTests(unittest.TestCase):
    """只忽略装饰变化；业务内容、坐标和沟通证据仍参与稳定判断。"""

    def test_online_label_changes_do_not_delay_ready_job(self):
        def page(text):
            """构造业务字段不变、活跃状态不断刷新的页面。"""
            snap = contact_page()
            ET.SubElement(snap.root[0], 'node', {'resource-id':'id/tv_description','text':'Go开发'})
            ET.SubElement(snap.root[0], 'node', {'resource-id':'id/boss_label_tv','text':text})
            return app.Snapshot(ET.tostring(snap.root))
        with tempfile.TemporaryDirectory() as tmp:
            device = app.UiautomatorDevice('phone',Path(tmp),client=Mock())
            pages = [page('刚刚活跃'),page('在线'),page('在线')]
            device.capture = Mock(side_effect=pages)
            with patch.object(app.time,'sleep'), patch.object(app.time,'perf_counter',side_effect=[0,.3,.4]):
                result = device.after_action('after-tap')
            self.assertIs(result,pages[1])
            self.assertEqual(device.capture.call_count,2)

    def test_business_identity_text_geometry_and_draft_changes_remain_unstable(self):
        for rid, attribute, value in [('tv_job_name','text','另一个岗位'),
                                      ('btn_chat','bounds','[50,200][1000,300]')]:
            with self.subTest(rid=rid):
                first, changed = contact_page(), contact_page()
                changed.unique(rid=rid).set(attribute,value)
                self.assertNotEqual(first.stability_key(),changed.stability_key())
        chat, draft = contact_page('chat'), contact_page('chat')
        draft.unique(rid='editText_with_scrollbar').set('text','用户草稿')
        self.assertNotEqual(chat.stability_key(),draft.stability_key())
        self.assertNotEqual(chat.stability_key(),contact_page('chat',marker=False).stability_key())
        first, changed = list_page(), list_page()
        changed.unique(rid='tv_position_name').set('bounds','[50,600][800,700]')
        self.assertNotEqual(first.stability_key(),changed.stability_key())

    def test_viewport_is_shared_only_within_one_poll_and_refreshed_before_click(self):
        raw = ET.tostring(list_page().root)
        display = b'mOverrideDisplayInfo=DisplayInfo{displayId 0, rotation 0, app 1080 x 2320, density 480}'
        with tempfile.TemporaryDirectory() as tmp:
            client = Mock()
            client.dump_hierarchy.return_value = raw
            device = app.UiautomatorDevice('phone',Path(tmp),client=client)
            device.call = Mock(return_value=display)
            device.after_action('after-scroll',stable=True)
            self.assertEqual(device.call.call_count,1)
            before = device.capture('before-tap')
            self.assertEqual(device.call.call_count,2)
            device.after_action = Mock(return_value=before)
            device.tap(before,before.unique(rid='tv_position_name'))
            self.assertEqual(device.call.call_args_list[-2].args,('shell','dumpsys','display'))
            self.assertEqual(device.call.call_args_list[-1].args[:3],('shell','input','tap'))

    def test_rotation_during_poll_refreshes_usable_display_size(self):
        first = ET.tostring(list_page().root)
        rotated = first.replace(b'rotation="0"',b'rotation="1"')
        displays = [b'mOverrideDisplayInfo=DisplayInfo{displayId 0, rotation 0, app 1080 x 2320, density 480}',
                    b'mOverrideDisplayInfo=DisplayInfo{displayId 0, rotation 1, app 2320 x 1080, density 480}']
        with tempfile.TemporaryDirectory() as tmp:
            client = Mock()
            client.dump_hierarchy.side_effect = [first,rotated]
            device = app.UiautomatorDevice('phone',Path(tmp),client=client)
            device.call = Mock(side_effect=displays)
            device._polling = True
            device.capture()
            result = device.capture()
            self.assertEqual((result.width,result.height),(2320,1080))
            self.assertEqual(device.call.call_count,2)
            self.assertEqual(device.metrics['fallbacks'],0)


class ListQualificationTests(unittest.TestCase):
    """列表只提前拦截详情原本就会待核的明确资格要求。"""

    def test_extracts_unique_unlabelled_tags_and_prefilters_high_requirements(self):
        row = list_page('5-10年','硕士').rows()[0]
        self.assertEqual((row['experience'],row['degree']),('5-10年','硕士'))
        self.assertEqual(app.prefilter_job(row,app.Criteria())['status'],'review')
        self.assertEqual(app.prefilter_job(list_page().rows()[0],app.Criteria())['status'],'candidate')

    def test_ambiguous_or_missing_tags_require_detail_instead_of_guessing(self):
        row = list_page('3-5年','本科','<node text="硕士"/><node text="5-10年"/>').rows()[0]
        self.assertEqual((row['experience'],row['degree']),('',''))
        self.assertEqual(app.prefilter_job(row,app.Criteria())['status'],'candidate')


class NegativeCacheTests(unittest.TestCase):
    """短期缓存只阻止重复读拒绝项，不授权任何沟通。"""

    def test_rejection_survives_new_batch_but_expires_and_tracks_changed_fields(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(app.time,'time',return_value=1000) as clock:
            path = Path(tmp)/'negative-cache.json'
            cache = app.NegativeCache(path,app.Criteria(),'one')
            rejected = job(jd='Go Agent开发')
            cache.remember(rejected,job(),app.evaluate_job(rejected,app.Criteria()))
            hit = app.NegativeCache(path,app.Criteria(),'one').lookup(job())
            self.assertEqual(hit['status'],'skipped')
            for field,value in [('hr','另一位招聘人'),('salary','20-25K'),('location','深圳·福田'),
                                ('experience','1-3年'),('degree','大专'),('digest','新的岗位摘要')]:
                with self.subTest(field=field):
                    self.assertIsNone(cache.lookup(job(**{field:value})))
            self.assertIsNone(app.NegativeCache(path,app.Criteria(salary_max=30),'one').lookup(job()))
            self.assertIsNone(app.NegativeCache(path,app.Criteria(),'two').lookup(job()))
            clock.return_value = 1000 + app.NEGATIVE_CACHE_TTL + 1
            self.assertIsNone(cache.lookup(job()))

    def test_ready_incomplete_and_uncertain_results_are_never_cached(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = app.NegativeCache(Path(tmp)/'negative-cache.json',app.Criteria(),'one')
            for value in [job(),job(jd_complete=False),job(jd='Go开发，第三方用工需了解')]:
                cache.remember(value,job(),app.evaluate_job(value,app.Criteria()))
                self.assertIsNone(cache.lookup(job()))

    def test_expired_or_damaged_cache_does_not_block_a_fresh_lookup(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'negative-cache.json'
            path.write_text('{broken',encoding='utf-8')
            cache = app.NegativeCache(path,app.Criteria(),'one')
            self.assertIsNone(cache.lookup(job()))
            app.write_json(path,dict(policy_version=app.NEGATIVE_CACHE_POLICY,criteria=app.asdict(app.Criteria()),
                account='one',entries={app.NegativeCache.signature(job()):
                    dict(expires_at=app.time.time()+100,status='skipped',reasons=['Agent/智能体岗位'])}))
            cache = app.NegativeCache(path,app.Criteria(),'one')
            self.assertIsNone(cache.lookup(job()))

    def test_missing_list_metadata_or_policy_change_invalidates_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'negative-cache.json'
            cache = app.NegativeCache(path,app.Criteria(),'one')
            rejected = job(jd='Go Agent开发')
            cache.remember(rejected,job(),app.evaluate_job(rejected,app.Criteria()))
            self.assertIsNone(cache.lookup(job(experience='')))
            data = json.loads(path.read_text(encoding='utf-8'))
            data['policy_version'] = -1
            app.write_json(path,data)
            self.assertIsNone(app.NegativeCache(path,app.Criteria(),'one').lookup(job()))

    def test_workflow_uses_rejection_cache_without_opening_or_contacting_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            cache = app.NegativeCache(out/'negative-cache.json',app.Criteria(),'one')
            rejected = job(jd='Go Agent开发')
            cache.remember(rejected,job(),app.evaluate_job(rejected,app.Criteria()))
            snap = Mock()
            snap.state.return_value = 'search_results'
            snap.rows.return_value = [job()]
            device = Mock(serial='phone')
            device.salary_filter.return_value = snap
            device.scroll.return_value = snap
            app.run_jobs(device,app.Criteria(),app.History(),app.Journal(out),1,1,'one',out)
            device.read_job.assert_not_called()
            device.contact_job.assert_not_called()
            report = json.loads((out/'results.json').read_text(encoding='utf-8'))
            self.assertTrue(report['records'][0]['negative_cache_hit'])


class SnapshotTests(unittest.TestCase):
    """页面树发生歧义或缺失时，不猜点击目标。"""

    def test_non_boss_page_rejected(self):
        with self.assertRaises(app.StopRun):
            app.Snapshot('<hierarchy><node package="other" text="Go" bounds="[0,0][1080,2400]"/></hierarchy>')

    def test_ambiguous_contact_control_rejected(self):
        snap = app.Snapshot('<hierarchy><node package="com.hpbr.bosszhipin" bounds="[0,0][1080,2400]">'
                            '<node resource-id="id/btn_chat" text="立即沟通" bounds="[1,1][10,10]"/>'
                            '<node resource-id="id/btn_chat" text="立即沟通" bounds="[20,1][30,10]"/></node></hierarchy>')
        with self.assertRaises(app.StopRun):
            snap.unique(rid="btn_chat", text="立即沟通")


    def test_existing_search_word_is_not_deleted_and_retyped(self):
        snap = app.Snapshot('<hierarchy><node package="com.hpbr.bosszhipin" bounds="[0,0][1080,2400]">'
                            '<node resource-id="id/et_search" text="go" focused="true" bounds="[100,100][900,200]"/>'
                            '</node></hierarchy>')
        device = Mock()
        device.tap.return_value = snap
        app.Device.fill_ascii(device, snap, snap.unique(rid="et_search"), "go")
        device.call.assert_not_called()

    def test_existing_salary_selection_is_not_toggled_off(self):
        wrapper = '<hierarchy><node package="com.hpbr.bosszhipin" bounds="[0,0][1080,2400]">%s</node></hierarchy>'
        results = app.Snapshot(wrapper % ('<node resource-id="id/tv_search_hint" text="go"/>'
                                          '<node resource-id="id/tv_tab_label" text="筛选·1" bounds="[400,300][600,400]"/>'))
        panel = app.Snapshot(wrapper % ('<node resource-id="id/tv_condition_title" text="薪资待遇"/>'
                                       '<node resource-id="id/keywords_view_text" text="10-20K" selected="true" bounds="[400,1000][600,1100]"/>'
                                       '<node resource-id="id/btn_confirm" text="确定" bounds="[400,2200][1000,2300]"/>'))
        device = Mock()
        device.capture.return_value = results
        device.tap.side_effect = [panel, results]
        app.Device.salary_filter(device, "10-20K")
        self.assertEqual(device.tap.call_count, 2)

    def test_search_restores_folded_city_filter_before_verifying(self):
        wrapper = '<hierarchy><node package="com.hpbr.bosszhipin" bounds="[0,0][1080,2400]">%s</node></hierarchy>'
        base = '<node resource-id="id/tv_search_hint" text="go"/><node resource-id="id/tv_tab_label" text="职位"/>'
        folded = app.Snapshot(wrapper % base)
        expanded = app.Snapshot(wrapper % (base + '<node resource-id="id/tv_tab_label" text="深圳"/>'))
        input_page = app.Snapshot(wrapper % ('<node resource-id="id/et_search" text="go"/>'
                                            '<node resource-id="id/tv_search" text="搜索"/>'))
        device = Mock()
        device.capture.return_value = folded
        device.tap.side_effect = [input_page, folded]
        device.fill_ascii.return_value = input_page
        device.scroll.return_value = expanded
        self.assertIs(app.Device.search(device, app.Criteria()), expanded)


def contact_page(kind="job", *, hr="李女士", title="Go开发工程师", company="示例公司",
                 continued=False, marker=True):
    """构造岗位身份与会话证据，用于验证立即沟通后的状态判断。"""
    if kind == "job":
        fields = [("tv_job_name", title), ("tv_boss_name", hr),
                  ("tv_boss_title", company + " • 招聘专员"),
                  ("btn_continue_chat" if continued else "btn_chat", "继续沟通" if continued else "立即沟通")]
    else:
        fields = [("editText_with_scrollbar", ""), ("tv_title", hr),
                  ("tv_position_name", title), ("tv_company_name", company)]
        if marker:
            fields.append(("tv_contact_time", "2026年11月6日开始沟通"))
    nodes = ''.join(f'<node resource-id="id/{rid}" text="{text}" bounds="[50,100][1000,200]"/>'
                    for rid, text in fields)
    return app.Snapshot('<hierarchy><node package="com.hpbr.bosszhipin" bounds="[0,0][1080,2400]">'
                        + nodes + '</node></hierarchy>')


class ContactFlowTests(unittest.TestCase):
    """新版流程只触发立即沟通，以岗位和会话证据核对结果。"""

    def test_contact_uses_one_click_without_keyboard(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal = app.Journal(Path(tmp))
            device = Mock()
            device.capture.return_value = contact_page()
            device.tap.return_value = contact_page("chat")
            device.check_contact = app.Device.check_contact
            app.Device.contact_job(device, job(), journal)
            self.assertEqual([e['status'] for e in journal.events], ['contacting', 'contacted'])
            self.assertEqual(device.tap.call_count, 1)
            device.call.assert_not_called()

    def test_wrong_recipient_never_counts_as_contacted(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal = app.Journal(Path(tmp))
            device = Mock()
            device.capture.side_effect = [contact_page(), contact_page("chat", hr="其他人")]
            device.tap.return_value = contact_page("chat", hr="其他人")
            device.check_contact = app.Device.check_contact
            with self.assertRaises(app.StopRun):
                app.Device.contact_job(device, job(), journal)
            self.assertEqual(journal.events[-1]['status'], 'unknown')
            self.assertEqual(device.tap.call_count, 1)

    def test_chat_without_contact_evidence_is_not_success(self):
        self.assertFalse(app.Device.check_contact(job(), contact_page("chat", marker=False)))

    def test_competitor_title_does_not_hide_chat_recipient(self):
        snap = contact_page("chat")
        ET.SubElement(snap.root[0], 'node', {'resource-id': 'id/tv_title', 'text': '你与该职位竞争者PK情况',
                                          'bounds': '[300,1600][900,1800]'})
        snap = app.Snapshot(ET.tostring(snap.root, encoding='unicode'))
        self.assertTrue(app.Device.check_contact(job(), snap))

    def test_chat_hint_is_not_user_draft(self):
        snap = contact_page("chat")
        snap.unique(rid='editText_with_scrollbar').set('text', '介绍自己回复率更高哦~')
        self.assertFalse(snap.has_chat_draft())
        snap.unique(rid='editText_with_scrollbar').set('text', '我的草稿')
        self.assertTrue(snap.has_chat_draft())

    def test_wrong_job_card_is_not_success(self):
        self.assertFalse(app.Device.check_contact(job(), contact_page("chat", title="别的岗位")))

    def test_current_job_continue_button_is_contact_evidence(self):
        self.assertTrue(app.Device.check_contact(job(), contact_page(continued=True)))

    def test_timeout_is_reconciled_without_second_click(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal = app.Journal(Path(tmp))
            device = Mock()
            device.capture.side_effect = [contact_page(), contact_page("chat")]
            device.tap.side_effect = app.StopRun("点按后读取超时")
            device.check_contact = app.Device.check_contact
            app.Device.contact_job(device, job(), journal)
            self.assertEqual(journal.events[-1]['status'], 'contacted')
            self.assertEqual(device.tap.call_count, 1)

    def test_existing_contact_does_not_click(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal = app.Journal(Path(tmp))
            device = Mock()
            device.capture.return_value = contact_page(continued=True)
            device.check_contact = app.Device.check_contact
            app.Device.contact_job(device, job(), journal)
            device.tap.assert_not_called()
            self.assertEqual(journal.events[-1]['status'], 'already_contacted')

    def test_unknown_result_blocks_next_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal = app.Journal(Path(tmp))
            device = Mock()
            device.capture.side_effect = [contact_page(), contact_page("chat", marker=False)]
            device.tap.side_effect = app.StopRun("点按后超时")
            device.check_contact = app.Device.check_contact
            with self.assertRaises(app.StopRun):
                app.Device.contact_job(device, job(), journal)
            self.assertTrue(app.Journal(Path(tmp)).contains(job()))
            self.assertEqual(journal.events[-1]['status'], 'unknown')
            self.assertEqual(device.tap.call_count, 1)


class WorkflowTests(unittest.TestCase):
    """验证从 JD 判断到沟通核对的顺序，不调用真实手机。"""

    def exercise(self, directory, *, history_duplicate=False, complete=True, unknown=False, seen=False):
        """用稳定列表模拟一个岗位，记录可观察的流程步骤。"""
        trace = []
        journal = app.Journal(Path(directory))
        row = job()
        snap = Mock()
        snap.state.return_value = 'search_results'
        snap.rows.return_value = [row]
        device = Mock(serial='phone')
        device.search.side_effect = lambda criteria: trace.append('search')
        device.salary_filter.return_value = snap
        device.capture.return_value = snap
        device.scroll.return_value = snap
        device.return_to_results.return_value = snap

        def read_job(row, current):
            """先读取 JD，再允许去重或点击。"""
            trace.append('read_jd')
            return job(jd_complete=complete), contact_page()

        def contact_job(value, log):
            """记录点击与核对步骤，不生成或输入定制消息。"""
            trace.extend(['click_contact', 'verify_contact'])
            log.record(value, 'contacting', '即将点击')
            if unknown:
                log.record(value, 'unknown', '未确认')
                raise app.StopRun('未确认沟通结果')
            log.record(value, 'contacted', '匹配会话已建立')
            return contact_page('chat')

        def contains(value):
            """记录列表和详情两处去重，重复岗位无需读取 JD。"""
            trace.append('dedup')
            return history_duplicate

        device.read_job.side_effect = read_job
        device.contact_job.side_effect = contact_job
        history = Mock()
        history.contains.side_effect = contains
        error = None
        try:
            app.run_jobs(device, app.Criteria(), history, journal, 1, 1, 'one', Path(directory),
                         seen_keys=[app.job_key(row)] if seen else ())
        except app.StopRun as exc:
            error = exc
        report = json.loads((Path(directory)/'results.json').read_text(encoding='utf-8'))
        return trace, report, device, error

    def test_run_contacts_matching_job_without_plan_or_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace, report, device, error = self.exercise(tmp)
            self.assertIsNone(error)
            self.assertEqual(trace, ['search', 'dedup', 'read_jd', 'dedup', 'click_contact', 'verify_contact'])
            self.assertEqual(report['contacted'], 1)
            self.assertEqual(report['records'][0]['status'], 'contacted')
            device.call.assert_not_called()
            self.assertNotIn('greeting', report['records'][0])

    def test_duplicate_is_not_clicked(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace, report, device, error = self.exercise(tmp, history_duplicate=True)
            self.assertIsNone(error)
            self.assertEqual(trace, ['search', 'dedup'])
            self.assertEqual(report['contacted'], 0)
            device.read_job.assert_not_called()
            device.contact_job.assert_not_called()

    def test_high_qualification_is_reviewed_on_list_without_opening_jd(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            snap = Mock()
            snap.state.return_value = 'search_results'
            snap.rows.return_value = [job(experience='5-10年')]
            device = Mock(serial='phone')
            device.salary_filter.return_value = snap
            device.scroll.return_value = snap
            app.run_jobs(device,app.Criteria(),app.History(),app.Journal(out),1,1,'one',out)
            device.read_job.assert_not_called()
            device.contact_job.assert_not_called()
            record = json.loads((out/'results.json').read_text(encoding='utf-8'))['records'][0]
            self.assertEqual((record['status'],record['stage']),('review','list'))

    def test_rejected_detail_is_remembered_for_next_explicit_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            row = job()
            rejected = job(jd='Go Agent开发')
            snap = Mock()
            snap.state.return_value = 'search_results'
            snap.rows.return_value = [row]
            device = Mock(serial='phone')
            device.salary_filter.return_value = snap
            device.scroll.return_value = snap
            device.read_job.return_value = rejected,contact_page()
            device.return_to_results.return_value = snap
            args = (device,app.Criteria(),app.History(),app.Journal(out),1,1,'one',out)
            app.run_jobs(*args)
            self.assertEqual(device.read_job.call_count,1)
            app.run_jobs(*args,new_batch=True)
            self.assertEqual(device.read_job.call_count,1)
            device.contact_job.assert_not_called()
            record = json.loads((out/'results.json').read_text(encoding='utf-8'))['records'][0]
            self.assertEqual(record['stage'],'negative_cache')

    def test_resuming_batch_does_not_reread_completed_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace, report, device, error = self.exercise(tmp, seen=True)
            self.assertIsNone(error)
            self.assertEqual(trace, ['search'])
            self.assertEqual(report['contacted'], 0)
            device.read_job.assert_not_called()
            device.contact_job.assert_not_called()

    def test_incomplete_jd_is_not_clicked(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, report, device, error = self.exercise(tmp, complete=False)
            self.assertIsNone(error)
            self.assertEqual(report['records'][0]['status'], 'review')
            device.contact_job.assert_not_called()

    def test_unknown_contact_stops_and_preserves_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, report, device, error = self.exercise(tmp, unknown=True)
            self.assertIsNotNone(error)
            self.assertFalse(report['complete'])
            self.assertEqual(report['records'][0]['status'], 'unknown')
            self.assertEqual(report['contacted'], 0)
            self.assertEqual(device.contact_job.call_count, 1)

    def test_new_dry_review_report_is_not_contact_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'results.json'
            p.write_text(json.dumps(dict(records=[dict(job(), status='review')])), encoding='utf-8')
            self.assertFalse(app.History([p]).contains(job()))

    def test_thirty_job_batch_resumes_at_twenty_nine_and_stops_after_one_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            records=[dict(job(title=f'Go开发岗位{i}'),status='contacted') for i in range(29)]
            app.write_json(out/'results.json',dict(version=3,started_at=app.now(),serial='phone',account='one',
                criteria=app.asdict(app.Criteria()),target=30,contacted=29,complete=False,records=records,timings={}))
            snap=Mock()
            snap.state.return_value='search_results'
            snap.rows.return_value=[job()]
            device=Mock(serial='phone')
            device.salary_filter.return_value=snap
            device.return_to_results.return_value=snap
            device.read_job.return_value=(job(),contact_page())
            def contact(value,journal):
                """仅最后一个新岗位产生沟通日志。"""
                journal.record(value,'contacted','已核对','proof.xml')
                return contact_page('chat')
            device.contact_job.side_effect=contact
            app.run_jobs(device,app.Criteria(),app.History(),app.Journal(out),30,1,'one',out)
            saved=json.loads((out/'results.json').read_text(encoding='utf-8'))
            self.assertTrue(saved['complete'])
            self.assertEqual(saved['contacted'],30)
            self.assertEqual(device.contact_job.call_count,1)

    def test_identity_mismatch_is_reviewed_and_next_job_can_continue(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            mismatch=job(company='匿名客户公司')
            agency=job(company='猎头机构')
            next_job=job(company='正常公司')
            snap=Mock()
            snap.state.return_value='search_results'
            snap.rows.return_value=[mismatch,next_job]
            device=Mock(serial='phone')
            device.salary_filter.return_value=snap
            device.return_to_results.return_value=snap
            device.read_job.side_effect=[app.JobIdentityMismatch(agency,contact_page(company='猎头机构')),
                                         (next_job,contact_page(company='正常公司'))]
            def contact(value,journal):
                """只有下一条身份匹配岗位可以产生沟通。"""
                journal.record(value,'contacted','已核对','proof.xml')
                return contact_page('chat',company='正常公司')
            device.contact_job.side_effect=contact
            app.run_jobs(device,app.Criteria(),app.History(),app.Journal(out),1,1,'one',out)
            saved=json.loads((out/'results.json').read_text(encoding='utf-8'))
            self.assertEqual([j['status'] for j in saved['records']],['review','contacted'])
            self.assertEqual(saved['records'][0]['detail_identity']['company'],'猎头机构')
            self.assertEqual(device.contact_job.call_count,1)
            self.assertEqual(device.contact_job.call_args.args[0]['company'],'正常公司')


if __name__ == "__main__":
    unittest.main()
