import os
import re
import copy
import sys
import yaml
import tempfile
from docassemble.webapp.files import SavedFile, get_ext_and_mimetype, make_package_zip
from docassemble.base.pandoc import word_to_markdown, convertible_mimetypes, convertible_extensions
from docassemble.base.core import DAObject, DADict, DAList
from docassemble.base.error import DAError
from docassemble.base.logger import logmessage
import docassemble.base.functions
import docassemble.base.parse
import docassemble.base.pdftk
import shutil
import datetime
import types

#from docassemble.base.util import prevent_dependency_satisfaction

TypeType = type(type(None))

__all__ = ['Playground', 'PlaygroundSection', 'indent_by', 'varname', 'DAField', 'DAFieldList', 'DAQuestion', 'DAQuestionDict', 'DAInterview', 'DAUpload', 'DAUploadMultiple', 'DAAttachmentList', 'DAAttachment', 'to_yaml_file', 'base_name', 'to_package_name', 'oneline','DAQuestionList','map_names','fill_in_field_attributes','attachment_download_html']

always_defined = set(["False", "None", "True", "dict", "i", "list", "menu_items", "multi_user", "role", "role_event", "role_needed", "speak_text", "track_location", "url_args", "x", "nav", "PY2", "string_types"])
replace_square_brackets = re.compile(r'\\\[ *([^\\]+)\\\]')
start_spaces = re.compile(r'^ +')
end_spaces = re.compile(r' +$')
spaces = re.compile(r'[ \n]+')
invalid_var_characters = re.compile(r'[^A-Za-z0-9_]+')
digit_start = re.compile(r'^[0-9]+')
newlines = re.compile(r'\n')
remove_u = re.compile(r'^u')

def attachment_download_html(url, label):
  return '<a href="' + url + '" download="">' + label + '</a>'

def fill_in_field_attributes(new_field, pdf_field_tuple):
    # Prevent Docassemble from finding any undefined variables. Trying to track down mysterious duplicate
    #try:
        # Let's guess the type of each field from the name / info from PDF
    new_field.variable = varname(pdf_field_tuple[0])
    variable_name_guess = new_field.variable.replace('_',' ').capitalize()        
    new_field.has_label = True
    if new_field.variable.endswith('_date'):
        new_field.field_type_guess = 'text'
        new_field.field_data_type_guess = 'date'
        new_field.variable_name_guess = 'Date of ' + new_field.variable[:-5].replace('_',' ')
    elif new_field.variable.endswith('_yes') or new_field.variable.endswith('_no'):
        new_field.field_type_guess = 'yesno'
        new_field.field_data_type_guess = None
        new_field.variable_name_guess = new_field.variable[:-3].replace('_',' ').capitalize() if new_field.variable.endswith('_no') else new_field.variable[:-4].replace('_',' ').capitalize()
    elif pdf_field_tuple[4] == '/Btn':
        new_field.field_type_guess = 'yesno'
        new_field.field_data_type_guess = None
        new_field.variable_name_guess = variable_name_guess
    elif pdf_field_tuple[4] == '/Sig':
        new_field.field_type_guess = 'signature'
        new_field.variable_name_guess = variable_name_guess
    else:
        new_field.field_type_guess = 'text'
        new_field.field_data_type_guess = 'text'
        new_field.variable_name_guess = variable_name_guess
    #except:
    #    raise Exception # prevent a NameError from being raised

class DADecoration(DAObject):
    def init(self, **kwargs):
        return super().init(**kwargs)

class DADecorationDict(DADict):
    def init(self, **kwargs):
        super().init(**kwargs)
        self.object_type = DADecoration
        self.auto_gather = False
        self.there_are_any = True

class DAAttachment(DAObject):
    def init(self, **kwargs):
        return super().init(**kwargs)

class DAAttachmentList(DAList):
    def init(self, **kwargs):
        super().init(**kwargs)
        self.object_type = DAAttachment
        self.auto_gather = False
    def url_list(self, project='default'):
        output_list = list()
        for x in self.elements:
            if x.type == 'md':
                output_list.append('[`' + x.markdown_filename + '`](' + docassemble.base.functions.url_of("playgroundfiles", section="template", file=x.markdown_filename, project=project) + ')')
            elif x.type == 'pdf':
                output_list.append('[`' + x.pdf_filename + '`](' + docassemble.base.functions.url_of("playgroundfiles", section="template", project=project) + ')')
            elif x.type == 'docx':
                output_list.append('[`' + x.docx_filename + '`](' + docassemble.base.functions.url_of("playgroundfiles", section="template", project=project) + ')')
        return docassemble.base.functions.comma_and_list(output_list)

class DAUploadMultiple(DAObject):
    def init(self, **kwargs):
        return super().init(**kwargs)

class DAUpload(DAObject):
    def init(self, **kwargs):
        return super().init(**kwargs)

class DAInterview(DAObject):
    def init(self, **kwargs):
        self.blocks = list()
        self.questions = DAQuestionDict()
        self.final_screen = DAQuestion()
        self.decorations = DADecorationDict()
        self.target_variable = None
        return super().init(**kwargs)
    def has_decorations(self):
        if self.decorations.gathered and len(self.decorations) > 0:
            return True
        return False
    def decoration_list(self):
        out_list = [["None", "No decoration"]]
        for key, data in self.decorations.items():
            out_list.append([key, '[EMOJI ' + str(data.fileref) + ', 1em] ' + str(key)])
        return out_list
    def package_info(self):
        info = dict()
        for field in ['dependencies', 'interview_files', 'template_files', 'module_files', 'static_files']:
            if field not in info:
                info[field] = list()
        info['readme'] = ""
        info['description'] = self.title
        info['version'] = "1.0"
        info['license'] = "The MIT License"
        info['url'] = "https://docassemble.org"
        for block in self.all_blocks():
            if hasattr(block, 'templates_used'):
                for template in block.templates_used:
                    if not re.search(r'^docassemble\.', template):
                        info['template_files'].append(template)
            if hasattr(block, 'static_files_used'):
                for static_file in block.static_files_used:
                    if not re.search(r'^docassemble\.', static_file):
                        info['static_files'].append(static_file)
        info['interview_files'].append(self.yaml_file_name())
        return info
    def yaml_file_name(self):
        return to_yaml_file(self.file_name)
    def all_blocks(self):
        seen = set()
        out = list()
        for block in self.blocks:
            if block not in seen:
                out.append(block)
                seen.add(block)
        for var in sorted(self.questions.keys()):
            if self.questions[var] not in seen:
                out.append(self.questions[var])
                seen.add(self.questions[var])
        return out
    def demonstrate(self):
        for block in self.all_blocks():
            block.demonstrated
    def source(self):
        return "---\n".join(map(lambda x: x.source(), self.all_blocks()))
    def known_source(self, skip=None):
        output = list()
        for block in self.all_blocks():
            if block is skip:
                continue
            try:
                output.append(block.source(follow_additional_fields=False))
            except:
                pass
        return "---\n".join(output)

class DAField(DAObject):
    def init(self, **kwargs):
        return super().init(**kwargs)

class DAFieldList(DAList):  
    def init(self, **kwargs):
        self.object_type = DAField
        self.auto_gather = False
        # self.gathered = True
        return super().init(**kwargs)
    def __str__(self):
        return docassemble.base.functions.comma_and_list(map(lambda x: '`' + x.variable + '`', self.elements))

class DAQuestion(DAObject):
    def init(self, **kwargs):
        self.field_list = DAFieldList()
        self.templates_used = set()
        self.static_files_used = set()
        return super().init(**kwargs)
    # def names_reduced(self):
    #     varsinuse = Playground().variables_from(self.interview.known_source(skip=self))
    #     var_list = sorted([field.variable for field in self.field_list])
    #     return [var for var in sorted(varsinuse['all_names_reduced']) if var not in var_list and var != self.interview.target_variable]
    # def other_variables(self):
    #     varsinuse = Playground().variables_from(self.interview.known_source(skip=self))
    #     var_list = sorted([field.variable for field in self.field_list])
    #     return [var for var in sorted(varsinuse['undefined_names']) if var not in var_list and var != self.interview.target_variable]
    def source(self, follow_additional_fields=True):
        content = ''
        if hasattr(self, 'is_mandatory') and self.is_mandatory:
            content += "mandatory: True\n"
        if self.type == 'question':
            done_with_content = False
            if hasattr(self,'has_mandatory_field') and not self.has_mandatory_field:
              content += "continue button field: " + varname(self.question_text) + "\n"
            elif hasattr(self, 'continue_button_field'):
              content += "continue button field: " + varname(self.continue_button_field) + "\n"
            content += "question: |\n" + indent_by(self.question_text, 2)
            if self.subquestion_text != "":
                content += "subquestion: |\n" + indent_by(self.subquestion_text, 2)
            if len(self.field_list) == 1:
                if self.field_list[0].field_type == 'yesno':
                    content += "yesno: " + varname(self.field_list[0].variable) + "\n"
                    done_with_content = True
                elif self.field_list[0].field_type == 'yesnomaybe':
                    content += "yesnomaybe: " + varname(self.field_list[0].variable) + "\n"
                    done_with_content = True
            if self.field_list[0].field_type == 'end_attachment':
                content += "buttons:\n  - Exit: exit\n  - Restart: restart\n"
                if self.attachments.gathered and len(self.attachments):
                    content += "attachment code: " + self.attachment_variable_name + "\n"
                    # TODO / FUTURE we could let this handle multiple forms at once
                    # content =+ "---\n"
                    # content += "code: |\n"
                    # for attachment in self.attachments:
                    # Put in some code to give each attachment its own variable name
                    for attachment in self.attachments: # We will only have ONE attachment
                        # TODO: if we really use multiple attachments, we need to change this
                        # So there is a unique variable name
                        content += "---\n"
                        content += "need: " + self.interview_label + "\n"
                        content += "attachment:\n"
                        content += "    variable name: " + self.attachment_variable_name + "\n"
                        content += "    name: " + oneline(attachment.name) + "\n"
                        content += "    filename: " + varname(attachment.name) + "\n"
                        if attachment.type == 'md':
                            content += "    content: " + oneline(attachment.content) + "\n"
                        elif attachment.type == 'pdf':
                            content += "    pdf template file: " + oneline(attachment.pdf_filename) + "\n"
                            self.templates_used.add(attachment.pdf_filename)
                            content += "    fields: " + "\n"
                            # for field, default, pageno, rect, field_type in attachment.fields:
                            # Switching to using a DAField, rather than a raw PDF field
                            for field in attachment.fields:
                                # Lets use the list-style, not dictionary style fields statement
                                # To avoid duplicate key error
                                if hasattr(field, 'field_data_type') and field.field_data_type == 'date':
                                  content += '      - "' + field.variable + '": ${ ' + varname(field.variable).format() + " }\n"
                                elif hasattr(field, 'field_data_type') and field.field_data_type == 'currency':
                                  content += '      - "' + field.variable + '": ${ currency(' + varname(field.variable) + " ) }\n"
                                else:
                                  # content += '      "' + field.variable + '": ${ ' + process_variable_name(varname(field.variable)) + " }\n"
                                  content += '      - "' + field.variable + '": ${ ' + map_names(varname(field.variable)) + " }\n"
                        elif attachment.type == 'docx':
                            content += "    docx template file: " + oneline(attachment.docx_filename) + "\n"
                            self.templates_used.add(attachment.docx_filename)
                done_with_content = True
            if not done_with_content:
                content += "fields:\n"
                for field in self.field_list:
                    if field.has_label:
                        content += "  - " + repr_str(field.label) + ": " + varname(field.variable) + "\n"
                    else:
                        content += "  - no label: " + varname(field.variable) + "\n"
                    if field.field_type == 'yesno':
                        content += "    datatype: yesno\n"
                    elif field.field_type == 'yesnomaybe':
                        content += "    datatype: yesnomaybe\n"
                    elif field.field_type == 'area':
                        content += "    input type: area\n"
                    elif field.field_type == 'file':
                        content += "    datatype: file\n"
                    elif field.field_data_type == 'integer':
                        content += "    datatype: integer\n"
                    elif field.field_data_type == 'number':
                        content += "    datatype: number\n"
                    elif field.field_data_type == 'currency':
                        content += "    datatype: currency\n"
                    elif field.field_data_type == 'date':
                        content += "    datatype: date\n"
                    elif field.field_data_type == 'email':
                        content += "    datatype: email\n"
                    elif field.field_data_type == 'range':
                        content += "    datatype: range\n"
                        content += "    min: " + field.range_min + "\n"
                        content += "    max: " + field.range_max + "\n"
                        content += "    step: " + field.range_step + "\n"
            # if self.interview.has_decorations() and self.decoration and self.decoration != 'None':
            #     content += "decoration: " + str(self.decoration) + "\n"
        elif self.type == 'signature':
            content += "signature: " + varname(self.field_list[0].variable) + "\n"
            self.under_text
            content += "question: |\n" + indent_by(self.question_text, 2)
            if self.subquestion_text != "":
                content += "subquestion: |\n" + indent_by(self.subquestion_text, 2)
            if self.under_text:
                content += "under: |\n" + indent_by(self.under_text, 2)
        elif self.type == 'code':
            content += "code: |\n" + indent_by(self.code, 2)
        elif self.type == 'interview order':
            content += "id: " + self.interview_label + "\n"
            content += "code: |\n"
            content += "  # This is a placeholder to control logic flow in this interview" + "\n"
            content += "  # We list one variable from each screen here, in order to control the order of questions\n"
            content += "  # To change the order, you can rearrange, or make conditional. If you make conditional here,\n"
            content += "  # You must also make sure it's conditional in the attachment block, or assign each variable \n"
            content += "  # on the optional screen to DAEmpty() \n"
            content += "  basic_questions_intro_screen \n" # trigger asking any intro questions at start of interview
            content += "  " + self.interview_label + "_intro" + "\n"
            for field in self.logic_list: 
              content += "  " + field + "\n" # We built this logic list by collecting the first field on each screen
            content += "  basic_questions_user_fields \n" # trigger asking the user details at the end of the interview         
            content += "  " + self.interview_label + " = True" + "\n"
        elif self.type == 'text_template':
            content += "template: " + varname(self.field_list[0].variable) + "\n"
            if hasattr(self, 'template_subject') and self.template_subject:
                content += "subject: " + oneline(self.template_subject) + "\n"
            if self.template_type == 'file':
                content += "content file: " + oneline(self.template_file) + "\n"
            else:
                content += "content: |\n" + indent_by(self.template_body, 2)
        elif self.type == 'template':
            content += "template: " + varname(self.field_list[0].variable) + "\n"
            content += "content file: " + oneline(self.template_file) + "\n"
            self.templates_used.add(self.template_file)
        elif self.type == 'metadata':
            content += "metadata:\n"
            content += "  title: " + oneline(self.title) + "\n"
            content += "  short title: " + oneline(self.short_title) + "\n"
            content += "  description: " + oneline(self.description) + "\n"
            content += "  original_form: " + oneline(self.original_form) + "\n"
            content += "  allowed courts: " + "\n"
            for court in self.allowed_courts.true_values():
              content += "    - " + oneline(court) + "\n"
            content += "  preferred court: " + oneline(self.preferred_court) + "\n"
            content += "  categories: " + "\n"
            for category in self.categories.true_values():
              content += "    - " + oneline(category) + "\n"
            if self.categories['Other']:
              for category in self.other_categories.split(','):
                content += "    - " + oneline(category) + "\n"
        elif self.type == 'metadata_code':
            content += "mandatory: True\n" # We need this block to run every time to build our metadata variable
            content += "code: |\n"
            content += "  if not defined('interview_metadata'):\n"
            content += "    interview_metadata = {}\n"
            content += "  interview_metadata['" + self.interview_label + "'] = {\n"
            content += "    'title': '" + oneline(self.title) + "',\n"
            content += "    'short title': '" + oneline(self.short_title) + "',\n"
            content += "    'description': '" + oneline(self.description) + "',\n"
            content += "    'original_form': '" + oneline(self.original_form) + "',\n"
            content += "    'allowed courts': " + "[\n"
            for court in self.allowed_courts.true_values():
              content += "      '" + oneline(court) + "',\n"
            content += "    ],\n"
            content += "    'preferred court': '" + oneline(self.preferred_court) + "',\n"
            content += "    'categories': [" + "\n"
            for category in self.categories.true_values():
              content += "      '" + oneline(category) + "',\n"
            if self.categories['Other']:
              for category in self.other_categories.split(','):
                content += "      '" + oneline(category.strip()) + "',\n"
            content += "    ],\n"
            content += "    'logic block variable': '" + self.interview_label + "',\n"
            content += "    'attachment block variable': '" + self.interview_label + "_attachment',\n"
            if hasattr(self, 'typical_role'):
              content += "    'typical role': '" + oneline(self.typical_role) + "',"
            content += "  }\n"
        elif self.type == 'modules':
            content += "modules:\n"
            for module in self.modules:
                content += " - " + str(module) + "\n"
        elif self.type == 'variables':
          content += "variable name: " + str(self).partition(' ')[0]  + "\n" # 'field_list' + "\n"
          content += "data:" + "\n"
          for field in self.field_list:
            content += "  - variable: " + varname(field.variable) + "\n"
            if hasattr(field, 'field_type'):
              content += "    " + "field_type: " + field.field_type + "\n"             
            if hasattr(field, 'field_data_type'):
              content += "    " + "field_data_type: " + field.field_data_type + "\n"
        elif self.type == 'includes':
          content += "include:\n"
          for include in self.includes:
            content += "  - " + include + "\n"
        elif self.type == 'interstitial':
          content += 'comment: |\n'
          content += indent_by(self.comment, 2) 
          content += 'continue button field: '+ self.continue_button_field + "\n"
          content += "question: |\n"
          content += indent_by(self.question_text, 2)
          content += "subquestion: |\n"
          content += indent_by(self.subquestion_text,2)
        # elif self.type == 'images':
        #     content += "images:\n"
        #     for key, value in self.interview.decorations.items():
        #         content += "  " + repr_str(key) + ": " + oneline(value.filename) + "\n"
        #         self.static_files_used.add(value.filename)
        #sys.stderr.write(content)
        return content

class DAQuestionList(DAList):
  def init(self, **kwargs): 
    super().init(**kwargs)
    self.object_type = DAQuestion
  def all_fields_used(self):
    fields = set()
    for question in self.elements:
      if hasattr(question,'field_list'):
        for field in question.field_list.elements:
          fields.add(field)
    return fields

class DAQuestionDict(DADict):
    def init(self, **kwargs):
        super().init(**kwargs)
        self.object_type = DAQuestion
        self.auto_gather = False
        self.gathered = True
        self.is_mandatory = False

class PlaygroundSection(object):
    def __init__(self, section='', project='default'):
        if docassemble.base.functions.this_thread.current_info['user']['is_anonymous']:
            raise DAError("Users must be logged in to create Playground objects")
        self.user_id = docassemble.base.functions.this_thread.current_info['user']['theid']
        self.current_info = docassemble.base.functions.this_thread.current_info
        self.section = section
        self.project = project
        self._update_file_list()
    def get_area(self):
        return SavedFile(self.user_id, fix=True, section='playground' + self.section)
    def _update_file_list(self):
        the_directory = directory_for(self.get_area(), self.project)
        self.file_list = sorted([f for f in os.listdir(the_directory) if f != '.placeholder' and os.path.isfile(os.path.join(the_directory, f))])
    def image_file_list(self):
        out_list = list()
        for the_file in self.file_list:
            extension, mimetype = get_ext_and_mimetype(the_file)
            if re.search(r'^image', mimetype):
                out_list.append(the_file)
        return out_list            
    def reduced_file_list(self):
        lower_list = [f.lower() for f in self.file_list]
        out_list = [f for f in self.file_list if os.path.splitext(f)[1].lower() in ['.md', '.pdf', '.docx'] or os.path.splitext(f)[0].lower() + '.md' not in lower_list]
        return out_list            
    def get_file(self, filename):
        return os.path.join(directory_for(self.get_area(), self.project), filename)
    def file_exists(self, filename):
        path = self.get_file(filename)
        if os.path.isfile(path):
            return True
        return False
    def delete_file(self, filename):
        area = self.get_area()
        the_filename = filename
        if self.project != 'default':
            the_filename = os.path.join(self.project, the_filename)
        area.delete_file(the_filename)
    def read_file(self, filename):
        path = self.get_file(filename)
        if path is None:
            return None
        with open(path, 'rU', encoding='utf-8') as fp:
            content = fp.read()
            return content
        return None
    def write_file(self, filename, content, binary=False):
        area = self.get_area()
        the_directory = directory_for(area, self.project)
        path = os.path.join(the_directory, filename)
        if binary:
            with open(path, 'wb') as ifile:
                ifile.write(content)
        else:
            with open(path, 'w', encoding='utf-8') as ifile:
                ifile.write(content)
        area.finalize()
    def commit(self):
        self.get_area().finalize()
    def copy_from(self, from_file, filename=None):
        if filename is None:
            filename = os.path.basename(from_file)
        to_path = self.get_file(filename)
        shutil.copy2(from_file, to_path)
        self.get_area().finalize()
        return filename
    def is_fillable_docx(self, filename):
        extension, mimetype = get_ext_and_mimetype(filename)
        if extension != "docx":
            return False
        if not self.file_exists(filename):
            return False
        path = self.get_file(filename)
        result_file = word_to_markdown(path, 'docx')
        if result_file is None:
            return False
        with open(result_file.name, 'rU', encoding='utf-8') as fp:
            result = fp.read()
        fields = set()
        for variable in re.findall(r'{{ *([^\} ]+) *}}', result):
            fields.add(docx_variable_fix(variable))
        for variable in re.findall(r'{%[a-z]* for [A-Za-z\_][A-Za-z0-9\_]* in *([^\} ]+) *%}', result):
            fields.add(docx_variable_fix(variable))
        if len(fields):
            return True
        return False
    def is_markdown(self, filename):
        extension, mimetype = get_ext_and_mimetype(filename)
        if extension == "md":
            return True
        return False
    def is_pdf(self, filename):
        extension, mimetype = get_ext_and_mimetype(filename)
        if extension == "pdf":
            return True
        return False
    def get_fields(self, filename):
        return docassemble.base.pdftk.read_fields(self.get_file(filename))
    def convert_file_to_md(self, filename, convert_variables=True):
        extension, mimetype = get_ext_and_mimetype(filename)
        if (mimetype and mimetype in convertible_mimetypes):
            the_format = convertible_mimetypes[mimetype]
        elif extension and extension in convertible_extensions:
            the_format = convertible_extensions[extension]
        else:
            return None
        if not self.file_exists(filename):
            return None
        path = self.get_file(filename)
        temp_file = word_to_markdown(path, the_format)
        if temp_file is None:
            return None
        out_filename = os.path.splitext(filename)[0] + '.md'
        if convert_variables:
            with open(temp_file.name, 'rU', encoding='utf-8') as fp:
                self.write_file(out_filename, replace_square_brackets.sub(fix_variable_name, fp.read()))
        else:
            shutil.copyfile(temp_file.name, self.get_file(out_filename))
        return out_filename
    def variables_from_file(self, filename):
        content = self.read_file(filename)
        if content is None:
            return None
        return Playground().variables_from(content)

class Playground(PlaygroundSection):
    def __init__(self):
        return super().__init__()
    def interview_url(self, filename):
        return docassemble.base.functions.url_of('interview', i='docassemble.playground' + str(self.user_id) + project_name(self.project) + ":" + filename)
    def write_package(self, pkgname, info):
        the_yaml = yaml.safe_dump(info, default_flow_style=False, default_style = '|')
        pg_packages = PlaygroundSection('packages')
        pg_packages.write_file(pkgname, the_yaml)
    def get_package_as_zip(self, pkgname):
        pg_packages = PlaygroundSection('packages')
        content = pg_packages.read_file(pkgname)
        if content is None:
            raise Exception("package " + str(pkgname) + " not found")
        info = yaml.load(content, Loader=yaml.FullLoader)
        author_info = dict()
        author_info['author name'] = self.current_info['user']['firstname'] + " " + self.current_info['user']['lastname']
        author_info['author email'] = self.current_info['user']['email']
        author_info['author name and email'] = author_info['author name'] + ", " + author_info['author email']
        author_info['first name'] = self.current_info['user']['firstname']
        author_info['last name'] = self.current_info['user']['lastname']
        author_info['id'] = self.user_id
        if self.current_info['user']['timezone']:
            the_timezone = self.current_info['user']['timezone']
        else:
            the_timezone = docassemble.base.functions.get_default_timezone()
        zip_file = make_package_zip(pkgname, info, author_info, the_timezone)
        file_number, extension, mimetype = docassemble.base.parse.save_numbered_file('docassemble-' + str(pkgname) + '.zip', zip_file.name)
        return file_number
    def variables_from(self, content):
        the_directory = directory_for(self.get_area(), self.project)
        interview_source = docassemble.base.parse.InterviewSourceString(content=content, directory=the_directory, path="docassemble.playground" + str(self.user_id) + project_name(self.project) + ":_temp.yml", package='docassemble.playground' + str(self.user_id) + project_name(self.project), testing=True)
        interview = interview_source.get_interview()
        temp_current_info = copy.deepcopy(self.current_info)
        temp_current_info['yaml_filename'] = "docassemble.playground" + str(self.user_id) + project_name(self.project) + ":_temp.yml"
        interview_status = docassemble.base.parse.InterviewStatus(current_info=temp_current_info)
        user_dict = docassemble.base.parse.get_initial_dict()
        user_dict['_internal']['starttime'] = datetime.datetime.utcnow()
        user_dict['_internal']['modtime'] = datetime.datetime.utcnow() 
        try:
            interview.assemble(user_dict, interview_status)
            has_error = False
        except Exception as errmess:
            has_error = True
            error_message = str(errmess)
            error_type = type(errmess)
            #logmessage("Failed assembly with error type " + str(error_type) + " and message: " + error_message)
        functions = set()
        modules = set()
        classes = set()
        fields_used = set()
        names_used = set()
        names_used.update(interview.names_used)
        area = SavedFile(self.user_id, fix=True, section='playgroundmodules')
        the_directory = directory_for(area, self.project)
        avail_modules = set([re.sub(r'.py$', '', f) for f in os.listdir(the_directory) if os.path.isfile(os.path.join(the_directory, f))])
        for question in interview.questions_list:
            names_used.update(question.mako_names)
            names_used.update(question.names_used)
            names_used.update(question.fields_used)
            fields_used.update(question.fields_used)
        for val in interview.questions:
            names_used.add(val)
            fields_used.add(val)
        for val in user_dict:
            if type(user_dict[val]) is types.FunctionType:
                functions.add(val)
            elif type(user_dict[val]) is TypeType or type(user_dict[val]) is types.ClassType:
                classes.add(val)
            elif type(user_dict[val]) is types.ModuleType:
                modules.add(val)
        for val in docassemble.base.functions.pickleable_objects(user_dict):
            names_used.add(val)
        for var in ['_internal']:
            names_used.discard(var)
        names_used = names_used.difference( functions | classes | modules | avail_modules )
        undefined_names = names_used.difference(fields_used | always_defined )
        for var in ['_internal']:
            undefined_names.discard(var)
        names_used = names_used.difference( undefined_names )
        all_names = names_used | undefined_names | fields_used
        all_names_reduced = all_names.difference( set(['url_args']) )
        return dict(names_used=names_used, undefined_names=undefined_names, fields_used=fields_used, all_names=all_names, all_names_reduced=all_names_reduced)

def fix_variable_name(match):
    var_name = match.group(1)
    var_name = end_spaces.sub(r'', var_name)
    var_name = spaces.sub(r'_', var_name)
    var_name = invalid_var_characters.sub(r'', var_name)
    var_name = digit_start.sub(r'', var_name)
    if len(var_name):
        return r'${ ' + var_name + ' }'
    return r''

def indent_by(text, num):
    if not text:
        return ""
    return (" " * num) + re.sub(r'\r*\n', "\n" + (" " * num), text).rstrip() + "\n"

def varname(var_name):
    var_name = start_spaces.sub(r'', var_name)
    var_name = end_spaces.sub(r'', var_name)
    var_name = spaces.sub(r'_', var_name)
    var_name = invalid_var_characters.sub(r'', var_name)
    var_name = digit_start.sub(r'', var_name)
    return var_name

def oneline(text):
    text = newlines.sub(r'', text)
    return text

def to_yaml_file(text):
    text = varname(text)
    text = re.sub(r'\..*', r'', text)
    text = re.sub(r'[^A-Za-z0-9]+', r'_', text)
    return text + '.yml'

def base_name(filename):
    return os.path.splitext(filename)[0]

def to_package_name(text):
    text = varname(text)
    text = re.sub(r'\..*', r'', text)
    text = re.sub(r'[^A-Za-z0-9]', r'', text)
    return text
    
def repr_str(text):
    return remove_u.sub(r'', repr(text))

def docx_variable_fix(variable):
    variable = re.sub(r'\\', '', variable)
    variable = re.sub(r'^([A-Za-z\_][A-Za-z\_0-9]*).*', r'\1', variable)
    return variable

def directory_for(area, current_project):
    if current_project == 'default':
        return area.directory
    else:
        return os.path.join(area.directory, current_project)

def project_name(name):
    return '' if name == 'default' else name


import re

def map_names(var_name):
  """Transform a PDF field name into a standardized object name, for a given set of specific cases in 
  our interview generator."""
  
  
  start_people_regex_string = (r"^(user|user\d+"
  + r"|other_party|other_party\d+"
  + r"|child|child\d+"
  + r"|witness|witness\d+)_")
  
  start_court_regex_string = r"^(court|court\d+)_"
  
  ending_map = [
    (start_people_regex_string + r"name_first$", r"\1.name.first"),
    (start_people_regex_string + r"name_middle$", r"\1.name.middle"),
    (start_people_regex_string + r"name_last$", r"\1.name.last"),
    (start_people_regex_string + r"name_suffix$", r"\1.name.suffix"),
    (start_people_regex_string + r"gender$", r"\1.gender"),
    (start_people_regex_string + r"birthdate$", r"\1.birthdate.format()"),
    (start_people_regex_string + r"age$", r"\1.age_in_years()"),
    (start_people_regex_string + r"email$", r"\1.email"),
    (start_people_regex_string + r"phone$", r"\1.phone_number"),
    (start_people_regex_string + r"address_block$", r"\1.address.block()"),
    (start_people_regex_string + r"address_street$", r"\1.address.address"),
    (start_people_regex_string + r"address_street2$", r"\1.address.unit"),
    (start_people_regex_string + r"address_city$", r"\1.address.city"),
    (start_people_regex_string + r"address_state$", r"\1.address.state"),
    (start_people_regex_string + r"address_zip$", r"\1.address.zip"),
    (start_people_regex_string + r"address_on_one_line$", r"\1.address.on_one_line()"),
    (start_people_regex_string + r"address_city_state_zip$", r"\1.address.line_two()"),
    (start_people_regex_string + r"signature$", r"\1.signature"),
    (start_people_regex_string + r"name_full$", r"str(\1)"),

    (start_court_regex_string + r"name$", r"\1"),
    # (start_court_regex_string + r"name_short$", not implemented),
    # (start_court_regex_string + r"division$", not implemented),
    (start_court_regex_string + r"address_county$", r"\1.address.county"),
    # We changed naming policy, but this is still used
    (start_court_regex_string + r"_county$", r"\1.address.county"),

    # signature_date is just signature_date,
    (r"^(docket_number)$", r"\1s[0]"),
    (r"^(docket_number)(\d+)$", r"\1s[\2-1]"),
    
    (r"^(plantiff|defendant|petitioner|respondent)$", r"str(\1s)"),
    (r"^(plantiffs|defendants|petitioners|respondents)$", r"str(\1)"),
  ]

  beginning_map = [
    (r"^(user)(\d+)(.*)$", r"\1s[\2-1]\3"),
    (r"^(user)(\..*)$", r"\1s[0]\2"),
    # Full name
    (r"^(str\()(user)(\d+)(\))$", r"\1\2s[\3-1]\4"),
    (r"^(str\()(user)(\))$", r"\1\2s[0]\3"),
    
    (r"^(other_party)(\d+)(.*)$", r"other_parties[\2-1]\3"),
    (r"^(other_party)(\..*)$", r"other_parties[0]\2"),
    # Full name
    (r"^(str\()(other_party)(\d+)(\))$", r"\1other_parties[\3-1]\4"),
    (r"^(str\()(other_party)(\))$", r"\1other_parties[0]\3"),
    
    (r"^(child)(\d+)(.*)$", r"\1ren[\2-1]\3"),
    (r"^(child)(\..*)$", r"\1ren[0]\2"),
    # Full name
    (r"^(str\()(child)(\d+)(\))$", r"\1\2ren[\3-1]\4"),
    (r"^(str\()(child)(\))$", r"\1\2ren[0]\3"),
    
    (r"^(witness)(\d+)(.*)$", r"\1es[\2-1]\3"),
    (r"^(witness)(\..*)$", r"\1es[0]\2"),
    # Full name
    (r"^(str\()(witness)(\d+)(\))$", r"\1\2es[\3-1]\4"),
    (r"^(str\()(witness)(\))$", r"\1\2es[0]\3"),
    
    (r"^(court)$", r"\1s[0]"),
    (r"^(court)(\d+)(.*)$", r"\1s[\2-1]\3"),
    (r"^(court)(\..*)$", r"\1s[0]\2"),
  ]

  for rule in ending_map:
    one_rule_applied = re.sub(rule[0], rule[1], var_name)
    if one_rule_applied != var_name:
      for rule in beginning_map:
        two_rules_applied = re.sub(rule[0], rule[1], one_rule_applied)
        if one_rule_applied != two_rules_applied:
          return two_rules_applied
      return one_rule_applied
  
  return var_name

'''
tests = [
    # Reserved
    "user_name_first",
    "user1_name_first",
    "user25_name_first",
    "user_name_full",
    "user1_name_full",
    "user3_name_full",
    "other_party_name_first",
    "other_party1_name_first",
    "other_party5_name_first",
    "other_party_name_full",
    "other_party1_name_full",
    "other_party2_name_full",
    "child_name_first",
    "child1_name_first",
    "child4_name_first",
    "child_name_full",
    "child1_name_full",
    "child5_name_full",
    "other_party37_address_zip",
    "user_address_street2",
    "witness_name_first",
    "witness1_name_first",
    "witness_name_full",
    "witness1_name_full",
    "court_name",
    "court1_name",
    "court_address_county",
    "court1_address_county",
    "docket_number",
    "docket_number1",
    "plantiff",
    "defendant",
    "petitioner",
    "respondent",
    "plantiffs",
    "defendants",
    "petitioners",
    "respondents",
    # Not reserved
    "my_user_name_last",
    "user_address_street2_zip",
    "user_address2_zip",
]
# tests = ["user_name_first","user25_name_last","other_party_name_full" ]
#if __name__ == 'main':

for test in tests:
  print(test, "=>", map_names(test))
  # map_names(test)
'''
