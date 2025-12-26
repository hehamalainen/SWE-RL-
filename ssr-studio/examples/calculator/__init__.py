# Simple Calculator Module
# This is a real, testable codebase for SSR demos

from .calculator import (
    Calculator,
    CalculatorError,
    DivisionByZeroError,
    InvalidInputError,
    evaluate_expression,
)

__all__ = [
    "Calculator",
    "CalculatorError", 
    "DivisionByZeroError",
    "InvalidInputError",
    "evaluate_expression",
]
