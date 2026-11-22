from kivy.app import App
from kivy.lang import Builder
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.utils import platform
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.properties import ObjectProperty, StringProperty
from kivy.metrics import dp
import os

from interviewer import Interview, MODULES, CAT_ORDER

try:
    from plyer import tts
except Exception:
    tts = None

KV = r'''
#:import dp kivy.metrics.dp
ScreenManager:
    HomeScreen:
        name: 'home'
    InterviewScreen:
        name: 'interview'
    ResultScreen:
        name: 'result'

<HomeScreen>:
    BoxLayout:
        orientation: 'vertical'
        padding: dp(22)
        spacing: dp(14)
        canvas.before:
            Color:
                rgba: .055, .075, .13, 1
            Rectangle:
                pos: self.pos
                size: self.size
        Label:
            text: 'MOCK INTERVIEW'
            font_size: '25sp'
            bold: True
            color: .35, .75, 1, 1
            size_hint_y: None
            height: dp(55)
        Label:
            text: 'Practice mock interviews for 32 job roles, offline. Answer, get scored, review your gaps.'
            font_size: '15sp'
            color: .88, .9, .95, 1
            text_size: self.width, None
            halign: 'center'
            size_hint_y: None
            height: dp(65)
        Label:
            text: 'SELECT JOB ROLE'
            size_hint_y: None
            height: dp(28)
            color: .7, .78, .9, 1
            halign: 'left'
        Spinner:
            id: module
            text: 'Tap to choose a role'
            values: []
            size_hint_y: None
            height: dp(52)
            background_color: .15, .2, .3, 1
            color: 1, 1, 1, 1
        Label:
            text: 'INTERVIEW DURATION (MINUTES)'
            size_hint_y: None
            height: dp(28)
            color: .7, .78, .9, 1
            halign: 'left'
        TextInput:
            id: duration
            text: '18'
            input_filter: 'int'
            multiline: False
            size_hint_y: None
            height: dp(50)
            font_size: '18sp'
            padding: dp(12), dp(12)
        Label:
            text: 'Offline mode • No API key • No internet required'
            color: .35, .85, .62, 1
            size_hint_y: None
            height: dp(36)
        Button:
            text: 'START INTERVIEW'
            size_hint_y: None
            height: dp(56)
            background_normal: ''
            background_color: .12, .48, .85, 1
            on_release: app.start_interview(module.text, duration.text)
        Widget:
            size_hint_y: 1
        Label:
            text: 'Answers are typed in this first Android version.'
            color: .62, .67, .75, 1
            font_size: '12sp'
            size_hint_y: None
            height: dp(28)

<InterviewScreen>:
    BoxLayout:
        orientation: 'vertical'
        padding: dp(16)
        spacing: dp(10)
        canvas.before:
            Color:
                rgba: .055, .075, .13, 1
            Rectangle:
                pos: self.pos
                size: self.size
        Label:
            id: progress
            text: 'MOCK INTERVIEW'
            size_hint_y: None
            height: dp(35)
            color: .35, .75, 1, 1
            bold: True
            font_size: '17sp'
        ScrollView:
            do_scroll_x: False
            Label:
                id: question
                text: ''
                color: 1, 1, 1, 1
                font_size: '19sp'
                text_size: self.width - dp(12), None
                size_hint_y: None
                height: self.texture_size[1] + dp(28)
                halign: 'left'
                valign: 'middle'
        TextInput:
            id: answer
            hint_text: 'Type your answer here...'
            multiline: True
            size_hint_y: .38
            font_size: '16sp'
            padding: dp(12), dp(12)
        BoxLayout:
            size_hint_y: None
            height: dp(50)
            spacing: dp(8)
            Button:
                text: 'HINT'
                on_release: app.show_hint()
            Button:
                text: 'REPEAT'
                on_release: app.repeat_question()
            Button:
                text: 'SKIP'
                on_release: app.submit_answer(True)
        Button:
            text: 'SUBMIT ANSWER'
            size_hint_y: None
            height: dp(54)
            background_normal: ''
            background_color: .12, .48, .85, 1
            on_release: app.submit_answer(False)
        Button:
            text: 'END INTERVIEW'
            size_hint_y: None
            height: dp(42)
            background_normal: ''
            background_color: .45, .18, .2, 1
            on_release: app.end_interview()

<ResultScreen>:
    BoxLayout:
        orientation: 'vertical'
        padding: dp(18)
        spacing: dp(12)
        canvas.before:
            Color:
                rgba: .055, .075, .13, 1
            Rectangle:
                pos: self.pos
                size: self.size
        Label:
            text: 'INTERVIEW RESULT'
            color: .35, .75, 1, 1
            bold: True
            font_size: '23sp'
            size_hint_y: None
            height: dp(50)
        ScrollView:
            Label:
                id: report
                text: ''
                color: 1, 1, 1, 1
                font_size: '15sp'
                text_size: self.width - dp(16), None
                size_hint_y: None
                height: self.texture_size[1] + dp(30)
                halign: 'left'
                valign: 'top'
        Button:
            text: 'BACK TO HOME'
            size_hint_y: None
            height: dp(54)
            on_release: app.root.current = 'home'
'''

class HomeScreen(Screen): pass
class InterviewScreen(Screen): pass
class ResultScreen(Screen): pass

class SAPInterviewApp(App):
    iv = None
    module_name = ''
    question_count = 0

    def build(self):
        self.title = 'Mock Interview'
        Window.clearcolor = (.055, .075, .13, 1)
        self.root = Builder.load_string(KV)
        # fill the role list from the question bank, grouped by category
        self.role_map = {}
        cats = [c for c in CAT_ORDER if any(r.get('cat') == c for r in MODULES.values())]
        for c in cats:
            for k, r in MODULES.items():
                if r.get('cat') == c:
                    self.role_map[r['name']] = k
        self.root.get_screen('home').ids.module.values = list(self.role_map.keys())
        return self.root

    def say(self, text):
        if not text:
            return
        if tts:
            try:
                tts.speak(text)
            except Exception:
                pass

    def start_interview(self, module_label, duration_text):
        key = self.role_map.get(module_label)
        if not key:
            self.root.get_screen('home').ids.module.text = 'Please choose a role first'
            return
        try:
            minutes = max(5, min(45, int(duration_text or '18')))
        except ValueError:
            minutes = 18
        self.module_name = MODULES[key]['name']
        self.iv = Interview(key, minutes)
        opening = self.iv.start()
        self.question_count = 0
        screen = self.root.get_screen('interview')
        screen.ids.answer.text = ''
        screen.ids.question.text = self.iv.cur['q']
        screen.ids.progress.text = self.module_name + '  •  Offline interview'
        self.root.current = 'interview'
        self.say(opening)

    def repeat_question(self):
        self.say(self.iv.cur['q'] if self.iv and self.iv.cur else '')

    def show_hint(self):
        if self.iv:
            hint = self.iv.hint()
            self.root.get_screen('interview').ids.progress.text = hint
            self.say(hint)

    def submit_answer(self, skipped=False):
        if not self.iv or not self.iv.cur:
            return
        screen = self.root.get_screen('interview')
        answer = '' if skipped else screen.ids.answer.text.strip()
        if not skipped and not answer:
            screen.ids.progress.text = 'Please type an answer, or tap SKIP.'
            return
        message, finished = self.iv.turn(answer, skipped=skipped)
        self.question_count += 1
        screen.ids.answer.text = ''
        if finished:
            self.show_result()
            return
        screen.ids.question.text = self.iv.cur['q']
        screen.ids.progress.text = f'{self.module_name}  •  Question {self.question_count + 1}'
        self.say(message)

    def end_interview(self):
        if self.iv and self.iv.log:
            self.show_result()
        else:
            self.root.current = 'home'

    def show_result(self):
        rep, avg = self.iv.finish()
        report_text = self.iv.report_text(rep, avg)
        try:
            path = os.path.join(self.user_data_dir, 'interview_report.txt')
            with open(path, 'w', encoding='utf-8') as f:
                f.write(report_text)
        except Exception:
            path = 'Report could not be saved.'
        strengths = '\n'.join('• ' + x for x in rep.get('strengths', [])) or '• None recorded'
        gaps = '\n'.join('• ' + x for x in rep.get('gaps', [])) or '• None recorded'
        study = '\n'.join('• ' + x for x in rep.get('study_plan', [])) or '• No specific study plan generated'
        summary = (f"Role: {self.module_name}\n\nScore: {rep.get('overall_score', avg)}/10\n"
                   f"Level reached: {rep.get('level_reached', 'beginner')}\n\n"
                   f"Verdict: {rep.get('verdict', '')}\n\nSTRENGTHS\n{strengths}\n\n"
                   f"AREAS TO IMPROVE\n{gaps}\n\nSTUDY PLAN\n{study}\n\n"
                   f"Full report saved inside app storage:\n{path}")
        self.root.get_screen('result').ids.report.text = summary
        self.root.current = 'result'
        self.say(f"Interview complete. Your score is {rep.get('overall_score', avg)} out of 10. {rep.get('verdict', '')}")

if __name__ == '__main__':
    SAPInterviewApp().run()
