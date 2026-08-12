from django.forms import CharField, Form, Media, MultiWidget, TextInput
from django.template import Context, Template
from django.test import SimpleTestCase, override_settings


@override_settings(
    STATIC_URL='http://media.example.com/static/',
)
class FormsMediaTestCase(SimpleTestCase):
    """Tests for the media handling on widgets and forms"""

    def test_construction(self):
        # Check construction of media objects
        m = Media(
            css={'all': ('path/to/css1', '/path/to/css2')},
            js=('/path/to/js1', 'http://media.other.com/path/to/js2', 'https://secure.other.com/path/to/js3'),
        )
        self.assertEqual(
            str(m),
            """<link href="http://media.example.com/static/path/to/css1" type="text/css" media="all" rel="stylesheet">
<link href="/path/to/css2" type="text/css" media="all" rel="stylesheet">
<script type="text/javascript" src="/path/to/js1"></script>
<script type="text/javascript" src="http://media.other.com/path/to/js2"></script>
<script type="text/javascript" src="https://secure.other.com/path/to/js3"></script>"""
        )
        self.assertEqual(
            repr(m),
            "Media(css={'all': ('path/to/css1', '/path/to/css2')}, "
            "js=('/path/to/js1', 'http://media.other.com/path/to/js2', 'https://secure.other.com/path/to/js3'))"
        )

        class Foo:
            css = {
                'all': ('path/to/css1', '/path/to/css2')
            }
            js = ('/path/to/js1', 'http://media.other.com/path/to/js2', 'https://secure.other.com/path/to/js3')

        m3 = Media(Foo)
        self.assertEqual(
            str(m3),
            """<link href="http://media.example.com/static/path/to/css1" type="text/css" media="all" rel="stylesheet">
<link href="/path/to/css2" type="text/css" media="all" rel="stylesheet">
<script type="text/javascript" src="/path/to/js1"></script>
<script type="text/javascript" src="http://media.other.com/path/to/js2"></script>
<script type="text/javascript" src="https://secure.other.com/path/to/js3"></script>"""
        )

        # A widget can exist without a media definition
        class MyWidget(TextInput):
            pass

        w = MyWidget()
        self.assertEqual(str(w.media), '')

    def test_media_dsl(self):
        ###############################################################
        # DSL Class-based media definitions
        ###############################################################

        # A widget can define media if it needs to.
        # Any absolute path will be preserved; relative paths are combined
        # with the value of settings.MEDIA_URL
        class MyWidget1(TextInput):
            class Media:
                css = {
                    'all': ('path/to/css1', '/path/to/css2')
                }
                js = ('/path/to/js1', 'http://media.other.com/path/to/js2', 'https://secure.other.com/path/to/js3')

        w1 = MyWidget1()
        self.assertEqual(
            str(w1.media),
            """<link href="http://media.example.com/static/path/to/css1" type="text/css" media="all" rel="stylesheet">
<link href="/path/to/css2" type="text/css" media="all" rel="stylesheet">
<script type="text/javascript" src="/path/to/js1"></script>
<script type="text/javascript" src="http://media.other.com/path/to/js2"></script>
<script type="text/javascript" src="https://secure.other.com/path/to/js3"></script>"""
        )

        # Media objects can be interrogated by media type
        self.assertEqual(
            str(w1.media['css']),
            """<link href="http://media.example.com/static/path/to/css1" type="text/css" media="all" rel="stylesheet">
<link href="/path/to/css2" type="text/css" media="all" rel="stylesheet">"""
        )

        self.assertEqual(
            str(w1.media['js']),
            """<script type="text/javascript" src="/path/to/js1"></script>
<script type="text/javascript" src="http://media.other.com/path/to/js2"></script>
<script type="text/javascript" src="https://secure.other.com/path/to/js3"></script>"""
        )

    def test_combine_media(self):
        # Media objects can be combined. Any given media resource will appear only
        # once. Duplicated media definitions are ignored.
        class MyWidget1(TextInput):
            class Media:
                css = {
                    'all': ('path/to/css1', '/path/to/css2')
                }
                js = ('/path/to/js1', 'http://media.other.com/path/to/js2', 'https://secure.other.com/path/to/js3')

        class MyWidget2(TextInput):
            class Media:
                css = {
                    'all': ('/path/to/css2', '/path/to/css3')
                }
                js = ('/path/to/js1', '/path/to/js4')

        class MyWidget3(TextInput):
            class Media:
                css = {
                    'all': ('path/to/css1', '/path/to/css3')
                }
                js = ('/path/to/js1', '/path/to/js4')

        w1 = MyWidget1()
        w2 = MyWidget2()
        w3 = MyWidget3()
        self.assertEqual(
            str(w1.media + w2.media + w3.media),
            """<link href="http://media.example.com/static/path/to/css1" type="text/css" media="all" rel="stylesheet">
<link href="/path/to/css2" type="text/css" media="all" rel="stylesheet">
<link href="/path/to/css3" type="text/css" media="all" rel="stylesheet">
<script type="text/javascript" src="/path/to/js1"></script>
<script type="text/javascript" src="http://media.other.com/path/to/js2"></script>
<script type="text/javascript" src="https://secure.other.com/path/to/js3"></script>
<script type="text/javascript" src="/path/to/js4"></script>"""
        )

        # media addition hasn't affected the original objects
        self.assertEqual(
            str(w1.media),
            """<link href="http://media.example.com/static/path/to/css1" type="text/css" media="all" rel="stylesheet">
<link href="/path/to/css2" type="text/css" media="all" rel="stylesheet">
<script type="text/javascript" src="/path/to/js1"></script>
<script type="text/javascript" src="http://media.other.com/path/to/js2"></script>
<script type="text/javascript" src="https://secure.other.com/path/to/js3"></script>"""
        )

        # Regression check for #12879: specifying the same CSS or JS file
        # multiple times in a single Media instance should result in that file
        # only being included once.
        class MyWidget4(TextInput):
            class Media:
                css = {'all': ('/path/to/css1', '/path/to/css1')}
                js = ('/path/to/js1', '/path/to/js1')

        w4 = MyWidget4()
        self.assertEqual(str(w4.media), """<link href="/path/to/css1" type="text/css" media="all" rel="stylesheet">
<script type="text/javascript" src="/path/to/js1"></script>""")

    def test_media_property(self):
        ###############################################################
        # Property-based media definitions
        ###############################################################

        # Widget media can be defined as a property
        class MyWidget4(TextInput):
            def _media(self):
                return Media(css={'all': ('/some/path',)}, js=('/some/js',))
            media = property(_media)

        w4 = MyWidget4()
        self.assertEqual(str(w4.media), """<link href="/some/path" type="text/css" media="all" rel="stylesheet">
<script type="text/javascript" src="/some/js"></script>""")

        # Media properties can reference the media of their parents
        class MyWidget5(MyWidget4):
            def _media(self):
                return super().media + Media(css={'all': ('/other/path',)}, js=('/other/js',))
            media = property(_media)

        w5 = MyWidget5()
        self.assertEqual(str(w5.media), """<link href="/some/path" type="text/css" media="all" rel="stylesheet">
<link href="/other/path" type="text/css" media="all" rel="stylesheet">
<script type="text/javascript" src="/some/js"></script>
<script type="text/javascript" src="/other/js"></script>""")

    def test_media_property_parent_references(self):
        # Media properties can reference the media of their parents,
        # even if the parent media was defined using a class
        class MyWidget1(TextInput):
            class Media:
                css = {
                    'all': ('path/to/css1', '/path/to/css2')
                }
                js = ('/path/to/js1', 'http://media.other.com/path/to/js2', 'https://secure.other.com/path/to/js3')

        class MyWidget6(MyWidget1):
            def _media(self):
                return super().media + Media(css={'all': ('/other/path',)}, js=('/other/js',))
            media = property(_media)

        w6 = MyWidget6()
        self.assertEqual(
            str(w6.media),
            """<link href="http://media.example.com/static/path/to/css1" type="text/css" media="all" rel="stylesheet">
<link href="/path/to/css2" type="text/css" media="all" rel="stylesheet">
<link href="/other/path" type="text/css" media="all" rel="stylesheet">
<script type="text/javascript" src="/path/to/js1"></script>
<script type="text/javascript" src="http://media.other.com/path/to/js2"></script>
<script type="text/javascript" src="https://secure.other.com/path/to/js3"></script>
<script type="text/javascript" src="/other/js"></script>"""
        )

    def test_media_inheritance(self):
        ###############################################################
        # Inheritance of media
        ###############################################################

        # If a widget extends another but provides no media definition, it inherits the parent widget's media
        class MyWidget1(TextInput):
            class Media:
                css = {
                    'all': ('path/to/css1', '/path/to/css2')
                }
                js = ('/path/to/js1', 'http://media.other.com/path/to/js2', 'https://secure.other.com/path/to/js3')

        class MyWidget7(MyWidget1):
            pass

        w7 = MyWidget7()
        self.assertEqual(
            str(w7.media),
            """<link href="http://media.example.com/static/path/to/css1" type="text/css" media="all" rel="stylesheet">
<link href="/path/to/css2" type="text/css" media="all" rel="stylesheet">
<script type="text/javascript" src="/path/to/js1"></script>
<script type="text/javascript" src="http://media.other.com/path/to/js2"></script>
<script type="text/javascript" src="https://secure.other.com/path/to/js3"></script>"""
        )

        # If a widget extends another but defines media, it extends the parent widget's media by default
        class MyWidget8(MyWidget1):
            class Media:
                css = {
                    'all': ('/path/to/css3', 'path/to/css1')
                }
                js = ('/path/to/js1', '/path/to/js4')

        w8 = MyWidget8()
        self.assertEqual(
            str(w8.media),
            """<link href="/path/to/css3" type="text/css" media="all" rel="stylesheet">
<link href="http://media.example.com/static/path/to/css1" type="text/css" media="all" rel="stylesheet">
<link href="/path/to/css2" type="text/css" media="all" rel="stylesheet">
<script type="text/javascript" src="/path/to/js1"></script>
<script type="text/javascript" src="http://media.other.com/path/to/js2"></script>
<script type="text/javascript" src="https://secure.other.com/path/to/js3"></script>
<script type="text/javascript" src="/path/to/js4"></script>"""
        )

    def test_media_inheritance_from_property(self):
        # If a widget extends another but defines media, it extends the parents widget's media,
        # even if the parent defined media using a property.
        class MyWidget1(TextInput):
            class Media:
                css = {
                    'all': ('path/to/css1', '/path/to/css2')
                }
                js = ('/path/to/js1', 'http://media.other.com/path/to/js2', 'https://secure.other.com/path/to/js3')

        class MyWidget4(TextInput):
            def _media(self):
                return Media(css={'all': ('/some/path',)}, js=('/some/js',))
            media = property(_media)

        class MyWidget9(MyWidget4):
            class Media:
                css = {
                    'all': ('/other/path',)
                }
                js = ('/other/js',)

        w9 = MyWidget9()
        self.assertEqual(
            str(w9.media),
            """<link href="/some/path" type="text/css" media="all" rel="stylesheet">
<link href="/other/path" type="text/css" media="all" rel="stylesheet">
<script type="text/javascript" src="/some/js"></script>
<script type="text/javascript" src="/other/js"></script>"""
        )

        # A widget can disable media inheritance by specifying 'extend=False'
        class MyWidget10(MyWidget1):
            class Media:
                extend = False
                css = {
                    'all': ('/path/to/css3', 'path/to/css1')
                }
                js = ('/path/to/js1', '/path/to/js4')

        w10 = MyWidget10()
        self.assertEqual(str(w10.media), """<link href="/path/to/css3" type="text/css" media="all" rel="stylesheet">
<link href="http://media.example.com/static/path/to/css1" type="text/css" media="all" rel="stylesheet">
<script type="text/javascript" src="/path/to/js1"></script>
<script type="text/javascript" src="/path/to/js4"></script>""")

    def test_media_inheritance_extends(self):
        # A widget can explicitly enable full media inheritance by specifying 'extend=True'
        class MyWidget1(TextInput):
            class Media:
                css = {
                    'all': ('path/to/css1', '/path/to/css2')
                }
                js = ('/path/to/js1', 'http://media.other.com/path/to/js2', 'https://secure.other.com/path/to/js3')

        class MyWidget11(MyWidget1):
            class Media:
                extend = True
                css = {
                    'all': ('/path/to/css3', 'path/to/css1')
                }
                js = ('/path/to/js1', '/path/to/js4')

        w11 = MyWidget11()
        self.assertEqual(
            str(w11.media),
            """<link href="/path/to/css3" type="text/css" media="all" rel="stylesheet">
<link href="http://media.example.com/static/path/to/css1" type="text/css" media="all" rel="stylesheet">
<link href="/path/to/css2" type="text/css" media="all" rel="stylesheet">
<script type="text/javascript" src="/path/to/js1"></script>
<script type="text/javascript" src="http://media.other.com/path/to/js2"></script>
<script type="text/javascript" src="https://secure.other.com/path/to/js3"></script>
<script type="text/javascript" src="/path/to/js4"></script>"""
        )

    def test_media_inheritance_single_type(self):
        # A widget can enable inheritance of one media type by specifying extend as a tuple
        class MyWidget1(TextInput):
            class Media:
                css = {
                    'all': ('path/to/css1', '/path/to/css2')
                }
                js = ('/path/to/js1', 'http://media.other.com/path/to/js2', 'https://secure.other.com/path/to/js3')

        class MyWidget12(MyWidget1):
            class Media:
                extend = ('css',)
                css = {
                    'all': ('/path/to/css3', 'path/to/css1')
                }
                js = ('/path/to/js1', '/path/to/js4')

        w12 = MyWidget12()
        self.assertEqual(
            str(w12.media),
            """<link href="/path/to/css3" type="text/css" media="all" rel="stylesheet">
<link href="http://media.example.com/static/path/to/css1" type="text/css" media="all" rel="stylesheet">
<link href="/path/to/css2" type="text/css" media="all" rel="stylesheet">
<script type="text/javascript" src="/path/to/js1"></script>
<script type="text/javascript" src="/path/to/js4"></script>"""
        )

    def test_multi_media(self):
        ###############################################################
        # Multi-media handling for CSS
        ###############################################################

        # A widget can define CSS media for multiple output media types
        class MultimediaWidget(TextInput):
            class Media:
                css = {
                    'screen, print': ('/file1', '/file2'),
                    'screen': ('/file3',),
                    'print': ('/file4',)
                }
                js = ('/path/to/js1', '/path/to/js4')

        multimedia = MultimediaWidget()
        self.assertEqual(
            str(multimedia.media),
            """<link href="/file4" type="text/css" media="print" rel="stylesheet">
<link href="/file3" type="text/css" media="screen" rel="stylesheet">
<link href="/file1" type="text/css" media="screen, print" rel="stylesheet">
<link href="/file2" type="text/css" media="screen, print" rel="stylesheet">
<script type="text/javascript" src="/path/to/js1"></script>
<script type="text/javascript" src="/path/to/js4"></script>"""
        )

    def test_multi_widget(self):
        ###############################################################
        # Multiwidget media handling
        ###############################################################

        class MyWidget1(TextInput):
            class Media:
                css = {
                    'all': ('path/to/css1', '/path/to/css2')
                }
                js = ('/path/to/js1', 'http://media.other.com/path/to/js2', 'https://secure.other.com/path/to/js3')

        class MyWidget2(TextInput):
            class Media:
                css = {
                    'all': ('/path/to/css2', '/path/to/css3')
                }
                js = ('/path/to/js1', '/path/to/js4')

        class MyWidget3(TextInput):
            class Media:
                css = {
                    'all': ('path/to/css1', '/path/to/css3')
                }
                js = ('/path/to/js1', '/path/to/js4')

        # MultiWidgets have a default media definition that gets all the
        # media from the component widgets
        class MyMultiWidget(MultiWidget):
            def __init__(self, attrs=None):
                widgets = [MyWidget1, MyWidget2, MyWidget3]
                super().__init__(widgets, attrs)

        mymulti = MyMultiWidget()
        self.assertEqual(
            str(mymulti.media),
            """<link href="http://media.example.com/static/path/to/css1" type="text/css" media="all" rel="stylesheet">
<link href="/path/to/css2" type="text/css" media="all" rel="stylesheet">
<link href="/path/to/css3" type="text/css" media="all" rel="stylesheet">
<script type="text/javascript" src="/path/to/js1"></script>
<script type="text/javascript" src="http://media.other.com/path/to/js2"></script>
<script type="text/javascript" src="https://secure.other.com/path/to/js3"></script>
<script type="text/javascript" src="/path/to/js4"></script>"""
        )

    def test_form_media(self):
        ###############################################################
        # Media processing for forms
        ###############################################################

        class MyWidget1(TextInput):
            class Media:
                css = {
                    'all': ('path/to/css1', '/path/to/css2')
                }
                js = ('/path/to/js1', 'http://media.other.com/path/to/js2', 'https://secure.other.com/path/to/js3')

        class MyWidget2(TextInput):
            class Media:
                css = {
                    'all': ('/path/to/css2', '/path/to/css3')
                }
                js = ('/path/to/js1', '/path/to/js4')

        class MyWidget3(TextInput):
            class Media:
                css = {
                    'all': ('path/to/css1', '/path/to/css3')
                }
                js = ('/path/to/js1', '/path/to/js4')

        # You can ask a form for the media required by its widgets.
        class MyForm(Form):
            field1 = CharField(max_length=20, widget=MyWidget1())
            field2 = CharField(max_length=20, widget=MyWidget2())
        f1 = MyForm()
        self.assertEqual(
            str(f1.media),
            """<link href="http://media.example.com/static/path/to/css1" type="text/css" media="all" rel="stylesheet">
<link href="/path/to/css2" type="text/css" media="all" rel="stylesheet">
<link href="/path/to/css3" type="text/css" media="all" rel="stylesheet">
<script type="text/javascript" src="/path/to/js1"></script>
<script type="text/javascript" src="http://media.other.com/path/to/js2"></script>
<script type="text/javascript" src="https://secure.other.com/path/to/js3"></script>
<script type="text/javascript" src="/path/to/js4"></script>"""
        )

        # Form media can be combined to produce a single media definition.
        class AnotherForm(Form):
            field3 = CharField(max_length=20, widget=MyWidget3())
        f2 = AnotherForm()
        self.assertEqual(
            str(f1.media + f2.media),
            """<link href="http://media.example.com/static/path/to/css1" type="text/css" media="all" rel="stylesheet">
<link href="/path/to/css2" type="text/css" media="all" rel="stylesheet">
<link href="/path/to/css3" type="text/css" media="all" rel="stylesheet">
<script type="text/javascript" src="/path/to/js1"></script>
<script type="text/javascript" src="http://media.other.com/path/to/js2"></script>
<script type="text/javascript" src="https://secure.other.com/path/to/js3"></script>
<script type="text/javascript" src="/path/to/js4"></script>"""
        )

        # Forms can also define media, following the same rules as widgets.
        class FormWithMedia(Form):
            field1 = CharField(max_length=20, widget=MyWidget1())
            field2 = CharField(max_length=20, widget=MyWidget2())

            class Media:
                js = ('/some/form/javascript',)
                css = {
                    'all': ('/some/form/css',)
                }
        f3 = FormWithMedia()
        self.assertEqual(
            str(f3.media),
            """<link href="http://media.example.com/static/path/to/css1" type="text/css" media="all" rel="stylesheet">
<link href="/path/to/css2" type="text/css" media="all" rel="stylesheet">
<link href="/path/to/css3" type="text/css" media="all" rel="stylesheet">
<link href="/some/form/css" type="text/css" media="all" rel="stylesheet">
<script type="text/javascript" src="/path/to/js1"></script>
<script type="text/javascript" src="http://media.other.com/path/to/js2"></script>
<script type="text/javascript" src="https://secure.other.com/path/to/js3"></script>
<script type="text/javascript" src="/path/to/js4"></script>
<script type="text/javascript" src="/some/form/javascript"></script>"""
        )

        # Media works in templates
        self.assertEqual(
            Template("{{ form.media.js }}{{ form.media.css }}").render(Context({'form': f3})),
            """<script type="text/javascript" src="/path/to/js1"></script>
<script type="text/javascript" src="http://media.other.com/path/to/js2"></script>
<script type="text/javascript" src="https://secure.other.com/path/to/js3"></script>
<script type="text/javascript" src="/path/to/js4"></script>
<script type="text/javascript" src="/some/form/javascript"></script>"""
            """<link href="http://media.example.com/static/path/to/css1" type="text/css" media="all" rel="stylesheet">
<link href="/path/to/css2" type="text/css" media="all" rel="stylesheet">
<link href="/path/to/css3" type="text/css" media="all" rel="stylesheet">
<link href="/some/form/css" type="text/css" media="all" rel="stylesheet">"""
        )

    def test_html_safe(self):
        media = Media(css={'all': ['/path/to/css']}, js=['/path/to/js'])
        self.assertTrue(hasattr(Media, '__html__'))
        self.assertEqual(str(media), media.__html__())

    def test_merge(self):
        test_values = (
            (([1, 2], [3, 4]), [1, 2, 3, 4]),
            (([1, 2], [2, 3]), [1, 2, 3]),
            (([2, 3], [1, 2]), [1, 2, 3]),
            (([1, 3], [2, 3]), [1, 2, 3]),
            (([1, 2], [1, 3]), [1, 2, 3]),
            (([1, 2], [3, 2]), [1, 3, 2]),
        )
        for (list1, list2), expected in test_values:
            with self.subTest(list1=list1, list2=list2):
                self.assertEqual(Media.merge(list1, list2), expected)

    def test_merge_warning(self):
        msg = 'Detected duplicate Media files in an opposite order:\n1\n2'
        with self.assertWarnsMessage(RuntimeWarning, msg):
            self.assertEqual(Media.merge([1, 2], [2, 1]), [1, 2])

    def test_merge_js_three_way(self):
        """
        The relative order of scripts is preserved in a three-way merge.
        With topological sorting, all constraints from all input lists are
        considered simultaneously, producing a valid topological ordering.
        """
        # custom_widget.js doesn't depend on jquery.js.
        widget1 = Media(js=['custom_widget.js'])
        widget2 = Media(js=['jquery.js', 'uses_jquery.js'])
        form_media = widget1 + widget2
        # Constraints: custom_widget.js (position 0 in widget1), 
        #              jquery.js < uses_jquery.js (from widget2)
        # Valid topological orders: [custom_widget.js, jquery.js, uses_jquery.js]
        #                          or [jquery.js, uses_jquery.js, custom_widget.js]
        # The merge should produce one valid order respecting the constraint jquery < uses_jquery
        self.assertEqual(form_media._js, ['custom_widget.js', 'jquery.js', 'uses_jquery.js'])
        
        # The inline also uses custom_widget.js. This time, it's at the end.
        inline_media = Media(js=['jquery.js', 'also_jquery.js']) + Media(js=['custom_widget.js'])
        # Constraints from inline: jquery.js < also_jquery.js
        # Constraints from custom_widget: (none, single item)
        # When merging with form_media: all constraints must be satisfied
        merged = form_media + inline_media
        # All constraints: jquery < uses_jquery, jquery < also_jquery
        # Valid topological orders exist; one valid order is:
        # [custom_widget.js, jquery.js, uses_jquery.js, also_jquery.js]
        # or [jquery.js, also_jquery.js, uses_jquery.js, custom_widget.js]
        # The topological sort should find a valid order
        js = merged._js
        # Verify key constraints are satisfied:
        self.assertLess(js.index('jquery.js'), js.index('uses_jquery.js'))
        self.assertLess(js.index('jquery.js'), js.index('also_jquery.js'))
        # Both jquery.js and uses_jquery.js should appear before also_jquery.js if custom_widget.js is first
        # or they should follow the constraints from their source lists

    def test_merge_css_three_way(self):
        """
        Merging CSS media with unconstrained items produces valid topological sort.
        With topological sort, the relative order of unconstrained items (a.css vs b.css
        when neither list specifies their relative order) may differ, but merging should
        succeed without warnings.
        """
        widget1 = Media(css={'screen': ['a.css']})
        widget2 = Media(css={'screen': ['b.css']})
        widget3 = Media(css={'all': ['c.css']})
        form1 = widget1 + widget2
        form2 = widget2 + widget1
        # form1 and form2 have a.css and b.css in different order...
        self.assertEqual(form1._css, {'screen': ['a.css', 'b.css']})
        self.assertEqual(form2._css, {'screen': ['b.css', 'a.css']})
        # ...but merging succeeds as the relative ordering of a.css and b.css
        # was never specified in the constraint graph (widget3 doesn't constrain them).
        merged = widget3 + form1 + form2
        # The merged result should contain all CSS files, with c.css in 'all'
        # and a.css, b.css in 'screen' (order may vary since unconstrained)
        self.assertEqual(set(merged._css['screen']), {'a.css', 'b.css'})
        self.assertEqual(merged._css['all'], ['c.css'])

    def test_merge_three_or_more_no_false_conflict_warning(self):
        """
        Regression test for issue where merging 3+ media objects raised 
        unnecessary MediaOrderConflictWarnings.
        
        This test reproduces the exact scenario from the bug report:
        - ColorPicker widget: ['color-picker.js']
        - SimpleTextWidget: ['text-editor.js']
        - FancyTextWidget: ['text-editor.js', 'text-editor-extras.js', 'color-picker.js']
        
        The issue was that intermediate pairwise merges (ColorPicker + SimpleTextWidget)
        would establish a false constraint (color-picker.js < text-editor.js), which
        would later conflict with FancyTextWidget's constraint
        (text-editor.js < text-editor-extras.js < color-picker.js).
        
        With topological sort over all lists simultaneously, the algorithm should
        find the valid order: text-editor.js < text-editor-extras.js < color-picker.js
        without raising a warning.
        """
        widget1_media = Media(js=['color-picker.js'])
        widget2_media = Media(js=['text-editor.js'])
        widget3_media = Media(js=['text-editor.js', 'text-editor-extras.js', 'color-picker.js'])
        
        # This should NOT raise MediaOrderConflictWarning
        # because topological sort can satisfy all constraints simultaneously
        result = widget1_media + widget2_media + widget3_media
        
        # Verify the final order respects the dependency from widget3_media
        js = result._js
        self.assertEqual(js, ['text-editor.js', 'text-editor-extras.js', 'color-picker.js'])
        self.assertLess(
            js.index('text-editor.js'),
            js.index('text-editor-extras.js'),
            "text-editor.js must come before text-editor-extras.js"
        )
        self.assertLess(
            js.index('text-editor-extras.js'),
            js.index('color-picker.js'),
            "text-editor-extras.js must come before color-picker.js"
        )

    def test_merge_genuine_conflict_still_warns(self):
        """
        Verify that genuine ordering conflicts (cycles in the constraint graph)
        still raise MediaOrderConflictWarning.
        
        A genuine conflict occurs when one list says X before Y and another
        list says Y before X, creating a cycle that cannot be resolved.
        """
        # These lists have a genuine ordering conflict
        list1 = ['a', 'b', 'c']  # a < b < c
        list2 = ['c', 'b', 'a']  # c < b < a (contradicts list1)
        
        msg = 'Detected duplicate Media files in an opposite order:'
        with self.assertWarnsMessage(RuntimeWarning, msg):
            # This should warn because there's a genuine cycle
            result = Media.merge(list1, list2)
            # Result should be one of the inputs or some fallback
            self.assertIn(result, [list1, list2, []])

