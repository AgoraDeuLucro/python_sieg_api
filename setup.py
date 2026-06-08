from setuptools import setup

with open("README.md", "r") as arq:
    readme = arq.read()

setup(name='py_sieg',
    version='0.0.3',
    license='MIT License',
    author='Yuri Gomes',
    long_description=readme,
    long_description_content_type="text/markdown",
    author_email='yurialdegomes@gmail.com',
    keywords='sieg',
    description=u'Wrapper não oficial do Sieg',
    packages=['py_sieg'],
    install_requires=['requests'],)