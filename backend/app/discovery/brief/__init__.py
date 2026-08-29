"""The search brief: what the user already knows about the target.

This package is imported from both directions - ``matching`` reads the gender
lexicon, while ``brief.apply`` writes into ``matching`` and ``loop`` - so the
package initialiser deliberately imports **nothing**. Import the submodule you
need (``brief.model``, ``brief.parse``, ``brief.gender``, ``brief.apply``) and the
cycle cannot form.
"""
