import copy
from enum import Enum

from brewparse import parse_program
from env_v3 import EnvironmentManager
from intbase import InterpreterBase, ErrorType
from type_valuev3 import Type, Value, create_value, get_printable


class ExecStatus(Enum):
    CONTINUE = 1
    RETURN = 2


# Main interpreter class
class Interpreter(InterpreterBase):
    # constants
    NIL_VALUE = create_value(InterpreterBase.NIL_DEF)
    TRUE_VALUE = create_value(InterpreterBase.TRUE_DEF)
    BIN_OPS = {"+", "-", "*", "/", "==", "!=", ">", ">=", "<", "<=", "||", "&&"}

    # methods
    def __init__(self, console_output=True, inp=None, trace_output=False):
        super().__init__(console_output, inp)
        self.trace_output = trace_output
        self.__setup_ops()

    # run a program that's provided in a string
    # usese the provided Parser found in brewparse.py to parse the program
    # into an abstract syntax tree (ast)
    def run(self, program):
        ast = parse_program(program)
        self.env = EnvironmentManager()
        self.__set_up_function_table(ast)
        main_func = self.__get_func_by_name("main", 0)
        self.__run_statements(main_func.get("statements"))

    def __set_up_function_table(self, ast):
        self.func_name_to_ast = {}
        for func_def in ast.get("functions"):
            dup = False
            func_name = func_def.get("name")
            num_params = len(func_def.get("args"))
            if func_name not in self.func_name_to_ast:
                self.func_name_to_ast[func_name] = {}
            else:
                dup = True
            self.func_name_to_ast[func_name][num_params] = func_def

            # TODO: check for duplicate function names
            if not dup:
                self.env.set(func_name, func_def)

    def __get_func_by_name(self, name, num_params):
        first_class = False
        if name not in self.func_name_to_ast:
            first_class = True
            assigned_func = self.env.get(name)
            if assigned_func is not None:
                try:
                    name = assigned_func.get("name")
                except:
                    return assigned_func.value()
            else:
                super().error(ErrorType.NAME_ERROR, f"Function {name} not found")
        candidate_funcs = self.func_name_to_ast[name]
        if len(candidate_funcs) > 1 and first_class:
            super().error(
                ErrorType.NAME_ERROR,
                f"Function {name} has multiple definitions, must specify number of parameters",
            )
        if num_params not in candidate_funcs:
            super().error(
                ErrorType.NAME_ERROR,
                f"Function {name} taking {num_params} params not found",
            )
        return candidate_funcs[num_params]

    def __run_statements(self, statements):
        self.env.push()
        for statement in statements:
            if self.trace_output:
                print(statement)
            status = ExecStatus.CONTINUE
            if statement.elem_type == InterpreterBase.FCALL_DEF:
                self.__call_func(statement)
            elif statement.elem_type == "=":
                self.__assign(statement)
            elif statement.elem_type == InterpreterBase.RETURN_DEF:
                status, return_val = self.__do_return(statement)
            elif statement.elem_type == Interpreter.IF_DEF:
                status, return_val = self.__do_if(statement)
            elif statement.elem_type == Interpreter.WHILE_DEF:
                status, return_val = self.__do_while(statement)

            if status == ExecStatus.RETURN:
                self.env.pop()
                return (status, return_val)

        self.env.pop()
        return (ExecStatus.CONTINUE, Interpreter.NIL_VALUE)

    def __call_func(self, call_node):

        func_name = call_node.get("name")
        if func_name == "print":
            return self.__call_print(call_node)
        if func_name == "inputi":
            return self.__call_input(call_node)
        if func_name == "inputs":
            return self.__call_input(call_node)
        try:
            actual_args = call_node.get("args")
            func_ast = self.__get_func_by_name(func_name, len(actual_args))
            formal_args = func_ast.get("args")
        except:
            super().error(ErrorType.TYPE_ERROR, "Function call not found")

        if len(actual_args) != len(formal_args):
            super().error(
                ErrorType.NAME_ERROR,
                f"Function {func_ast.get('name')} with {len(actual_args)} args not found",
            )
        self.env.push()
        self.env.ref_push()
        for formal_ast, actual_ast in zip(formal_args, actual_args):
            result = copy.deepcopy(self.__eval_expr(actual_ast))
            arg_name = formal_ast.get("name")
            if formal_ast.elem_type == InterpreterBase.REFARG_DEF:
                self.env.create(arg_name, result)
                self.env.ref_create(arg_name, actual_ast.get("name"))
            else:
                self.env.create(arg_name, result)
        _, return_val = self.__run_statements(func_ast.get("statements"))
        self.env.ref_pop()
        self.env.pop()
        return return_val

    def __call_print(self, call_ast):
        output = ""
        for arg in call_ast.get("args"):
            result = self.__eval_expr(arg)  # result is a Value object
            output = output + get_printable(result)
        super().output(output)
        return Interpreter.NIL_VALUE

    def __call_input(self, call_ast):
        args = call_ast.get("args")
        if args is not None and len(args) == 1:
            result = self.__eval_expr(args[0])
            super().output(get_printable(result))
        elif args is not None and len(args) > 1:
            super().error(
                ErrorType.NAME_ERROR, "No inputi() function that takes > 1 parameter"
            )
        inp = super().get_input()
        if call_ast.get("name") == "inputi":
            return Value(Type.INT, int(inp))
        if call_ast.get("name") == "inputs":
            return Value(Type.STRING, inp)

    def __assign(self, assign_ast):
        var_name = assign_ast.get("name")
        value_obj = self.__eval_expr(assign_ast.get("expression"))
        self.env.set(var_name, value_obj)
        if self.env.get_ref(var_name) is not None:
            self.env.ref_set(var_name, value_obj)

    def __eval_expr(self, expr_ast):
        # print("here expr")
        # print("type: " + str(expr_ast.elem_type))
        if expr_ast.elem_type == InterpreterBase.NIL_DEF:
            # print("getting as nil")
            return Interpreter.NIL_VALUE
        if expr_ast.elem_type == InterpreterBase.INT_DEF:
            return Value(Type.INT, expr_ast.get("val"))
        if expr_ast.elem_type == InterpreterBase.STRING_DEF:
            # print("getting as str")
            return Value(Type.STRING, expr_ast.get("val"))
        if expr_ast.elem_type == InterpreterBase.BOOL_DEF:
            return Value(Type.BOOL, expr_ast.get("val"))
        if expr_ast.elem_type == InterpreterBase.LAMBDA_DEF:
            return Value(Type.FUNC, expr_ast)
        if expr_ast.elem_type == InterpreterBase.VAR_DEF:
            var_name = expr_ast.get("name")
            val = self.env.get(var_name)
            if val is None:
                super().error(ErrorType.NAME_ERROR, f"Variable {var_name} not found")
            return val
        if expr_ast.elem_type == InterpreterBase.FCALL_DEF:
            return self.__call_func(expr_ast)
        if expr_ast.elem_type in Interpreter.BIN_OPS:
            return self.__eval_op(expr_ast)
        if expr_ast.elem_type == Interpreter.NEG_DEF:
            return self.__eval_unary(expr_ast, [Type.INT], lambda x: -1 * x)
        if expr_ast.elem_type == Interpreter.NOT_DEF:
            return self.__eval_unary(expr_ast, [Type.BOOL, Type.INT], lambda x: not x)



    def __eval_op(self, arith_ast):
        left_value_obj = self.__eval_expr(arith_ast.get("op1"))
        right_value_obj = self.__eval_expr(arith_ast.get("op2"))
        if not self.__compatible_types(
            arith_ast.elem_type, left_value_obj, right_value_obj
        ):
            super().error(
                ErrorType.TYPE_ERROR,
                f"Incompatible types for {arith_ast.elem_type} operation",
            )
        if hasattr(left_value_obj, 'elem_type') and left_value_obj.elem_type != 'func' and arith_ast.elem_type not in self.op_to_lambda[left_value_obj.type()]:
            super().error(
                ErrorType.TYPE_ERROR,
                f"Incompatible operator {arith_ast.elem_type} for type {left_value_obj.elem_type}",
            )
        
        elif hasattr(left_value_obj, 'elem_type') and left_value_obj.elem_type == 'func':
            if arith_ast.elem_type not in self.op_to_lambda[Type.FUNC]:
                super().error(
                    ErrorType.TYPE_ERROR,
                    f"Incompatible operator {arith_ast.elem_type} for type {left_value_obj.elem_type}",
                )
            f = self.op_to_lambda[Type.FUNC][arith_ast.elem_type]
        else:
            f = self.op_to_lambda[left_value_obj.type()][arith_ast.elem_type]
        # print("here eval")
        # print(arith_ast)
        # print("evaluating " + str(left_value_obj.type()) + " " + str(arith_ast.elem_type))
        # print("obj left: " + str(left_value_obj.value()))
        return f(left_value_obj, right_value_obj)

    def __compatible_types(self, oper, obj1, obj2):
        # DOCUMENT: allow comparisons ==/!= of anything against anything
        if oper in ["==", "!="]:
            return True
        elif oper in ["&&", "||", "+", "-", "*", "/"]:
            return (obj1.type() == Type.BOOL or obj1.type() == Type.INT) and (
                obj2.type() == Type.BOOL or obj2.type() == Type.INT
            )
        return obj1.type() == obj2.type()

    def __eval_unary(self, arith_ast, t, f):
        value_obj = self.__eval_expr(arith_ast.get("op1"))
        if value_obj.type() not in t:
            super().error(
                ErrorType.TYPE_ERROR,
                f"Incompatible type for {arith_ast.elem_type} operation",
            )
        if len(t) == 2:
            return Value(Type.BOOL, (bool)(f(value_obj.value())))
        return Value(t[0], f(value_obj.value()))

    def __setup_ops(self):
        self.op_to_lambda = {}
        # set up operations on integers
        self.op_to_lambda[Type.INT] = {}
        self.op_to_lambda[Type.INT]["+"] = lambda x, y: Value(
            x.type(), x.value() + y.value() if y.type() == Type.INT else (x.value() + 1 if y.value() else x.value())
        )
        self.op_to_lambda[Type.INT]["-"] = lambda x, y: Value(
            x.type(), x.value() - y.value() if y.type() == Type.INT else (x.value() - 1 if y.value() else x.value())
        )
        self.op_to_lambda[Type.INT]["*"] = lambda x, y: Value(
            x.type(), x.value() * y.value() if y.type() == Type.INT else (x.value() * 1 if y.value() else 0)
        )
        self.op_to_lambda[Type.INT]["/"] = lambda x, y: Value(
            x.type(), x.value() // y.value() if y.type() == Type.INT else (x.value() // 1 if y.value() else 0)
        )
        self.op_to_lambda[Type.INT]["=="] = lambda x, y: Value(
            Type.BOOL, (x.type() == y.type() or y.type() == Type.BOOL) and 
            ((x.value() != 0 and y.value() == True) or (x.value() == 0 and y.value() == False)) if y.type() == Type.BOOL else ((x.value() != 0 and y.value() != 0) or x.value() == 0 and y.value() == 0)
        )
        self.op_to_lambda[Type.INT]["!="] = lambda x, y: Value(
            Type.BOOL, (x.type() != y.type() and y.type() != Type.BOOL) or ((x.value() == 0 and y.value() == True) or (x.value() != 0 and y.value() == False))
        )
        self.op_to_lambda[Type.INT]["&&"] = lambda x, y: Value(
            Type.BOOL, (x.type() == y.type() or y.type() == Type.BOOL) and (bool)(x.value() and y.value())
        )
        self.op_to_lambda[Type.INT]["||"] = lambda x, y: Value(
            Type.BOOL, (x.type() == y.type() or y.type() == Type.BOOL) and (bool)(x.value() or y.value())
        )
        self.op_to_lambda[Type.INT]["<"] = lambda x, y: Value(
            Type.BOOL, x.value() < y.value()
        )
        self.op_to_lambda[Type.INT]["<="] = lambda x, y: Value(
            Type.BOOL, x.value() <= y.value()
        )
        self.op_to_lambda[Type.INT][">"] = lambda x, y: Value(
            Type.BOOL, x.value() > y.value()
        )
        self.op_to_lambda[Type.INT][">="] = lambda x, y: Value(
            Type.BOOL, x.value() >= y.value()
        )
        #  set up operations on strings
        self.op_to_lambda[Type.STRING] = {}
        self.op_to_lambda[Type.STRING]["+"] = lambda x, y: Value(
            x.type(), x.value() + y.value()
        )
        self.op_to_lambda[Type.STRING]["=="] = lambda x, y: Value(
            Type.BOOL, x.value() == y.value()
        )
        self.op_to_lambda[Type.STRING]["!="] = lambda x, y: Value(
            Type.BOOL, x.value() != y.value()
        )
        #  set up operations on bools
        self.op_to_lambda[Type.BOOL] = {}
        self.op_to_lambda[Type.BOOL]["&&"] = lambda x, y: Value(
            x.type(), (x.type() == y.type() or y.type() == Type.INT) and (bool)(x.value() and y.value())
        )
        self.op_to_lambda[Type.BOOL]["||"] = lambda x, y: Value(
            x.type(), (x.type() == y.type() or y.type() == Type.INT) and (bool)(x.value() or y.value())
        )
        self.op_to_lambda[Type.BOOL]["=="] = lambda x, y: Value(
            Type.BOOL, (x.type() == y.type() or y.type() == Type.INT) and ((x.value() == True and y.value() != 0) or (x.value() == False and y.value() == 0))
        )
        self.op_to_lambda[Type.BOOL]["!="] = lambda x, y: Value(
            Type.BOOL, (x.type() != y.type() and y.type() != Type.INT) or ((x.value() == True and y.value() == 0) or (x.value() == False and y.value() != 0))
        )
        self.op_to_lambda[Type.BOOL]["+"] = lambda x, y: Value(
            Type.INT, 1 + y.value() if y.type() == Type.INT and x.value() 
            else (y.value() if y.type() == Type.INT 
                  else (1 + 1 if x.value() and y.value() 
                        else (1 if x.value() ^ y.value() 
                              else 0)))
        )
        self.op_to_lambda[Type.BOOL]["-"] = lambda x, y: Value(
            Type.INT, 1 - y.value() if y.type() == Type.INT and x.value() 
            else (-1 * y.value() if y.type() == Type.INT 
                  else (0 if x.value() and y.value() 
                        else (1 if x.value() and not y.value() 
                              else (-1 if not x.value() and y.value() 
                                    else 0))))
        )
        self.op_to_lambda[Type.BOOL]["*"] = lambda x, y: Value(
            Type.INT, y.value() if y.type() == Type.INT and x.value() 
            else (0 if y.type() == Type.INT 
                  else (1 if x.value() and y.value() 
                        else 0))
        )
        self.op_to_lambda[Type.BOOL]["/"] = lambda x, y: Value(
            Type.INT, 1 // y.value() if y.type() == Type.INT and x.value() 
            else (0 if y.type() == Type.INT 
                  else (1 if x.value() and y.value() 
                        else x.value() // y.value()))
        )
        self.op_to_lambda[Type.FUNC] = {}
        self.op_to_lambda[Type.FUNC]["=="] = lambda x, y: Value(
            Type.BOOL, x is y if hasattr(x, 'elem_type') and hasattr(y,'elem_type') 
                else (x.value() is y.value() if hasattr(x, 'type') and hasattr(y, 'type') 
                      else(x.value() is y if hasattr(x, 'type') and hasattr(y, 'elem_type') 
                           else(x is y.value() if hasattr(x, 'elem_type') and hasattr(y, 'type')
                                else (x is y))))
        )
        self.op_to_lambda[Type.FUNC]["!="] = lambda x, y: Value(
            Type.BOOL, x is not y if hasattr(x, 'elem_type') and hasattr(y,'elem_type') 
                else (x.value() is not y.value() if hasattr(x, 'type') and hasattr(y, 'type') 
                      else(x.value() is not y if hasattr(x, 'type') and hasattr(y, 'elem_type') 
                           else(x is not y.value() if hasattr(x, 'elem_type') and hasattr(y, 'type')
                                else (x is not y))))
        )
        #  set up operations on nil
        self.op_to_lambda[Type.NIL] = {}
        self.op_to_lambda[Type.NIL]["=="] = lambda x, y: Value(
            Type.BOOL, (x.type() == y.type() if hasattr(y, 'type') 
                        else x.type() == y) or (x.value() == y.value() if hasattr(y, 'type') 
                                                else x.value() == y)
        )
        self.op_to_lambda[Type.NIL]["!="] = lambda x, y: Value(
            Type.BOOL, (x.type() != y.type() if hasattr(y, 'type') 
                        else x.type() != y) or (x.value() != y.value() if hasattr(y, 'type') 
                                                else x.value() != y)
        )

    def __do_if(self, if_ast):
        cond_ast = if_ast.get("condition")
        result = self.__eval_expr(cond_ast)
        if result.type() == Type.INT:
            result = Value(Type.BOOL, result.value() != 0)
        elif result.type() != Type.BOOL:
            super().error(
                ErrorType.TYPE_ERROR,
                "Incompatible type for if condition",
            )
        if result.value():
            statements = if_ast.get("statements")
            status, return_val = self.__run_statements(statements)
            return (status, return_val)
        else:
            else_statements = if_ast.get("else_statements")
            if else_statements is not None:
                status, return_val = self.__run_statements(else_statements)
                return (status, return_val)

        return (ExecStatus.CONTINUE, Interpreter.NIL_VALUE)

    def __do_while(self, while_ast):
        cond_ast = while_ast.get("condition")
        run_while = Interpreter.TRUE_VALUE
        while run_while.value():
            run_while = self.__eval_expr(cond_ast)
            if run_while.type() == Type.INT:
                run_while = Value(Type.BOOL, run_while.value() != 0)
            elif run_while.type() != Type.BOOL:
                super().error(
                    ErrorType.TYPE_ERROR,
                    "Incompatible type for while condition",
                )
            if run_while.value():
                statements = while_ast.get("statements")
                status, return_val = self.__run_statements(statements)
                if status == ExecStatus.RETURN:
                    return status, return_val

        return (ExecStatus.CONTINUE, Interpreter.NIL_VALUE)

    def __do_return(self, return_ast):
        expr_ast = return_ast.get("expression")
        if expr_ast is None:
            return (ExecStatus.RETURN, Interpreter.NIL_VALUE)
        value_obj = copy.deepcopy(self.__eval_expr(expr_ast))
        return (ExecStatus.RETURN, value_obj)

def main():
    program = 'func foo(ref x, delta) { /* x passed by reference, delta passed by value */\
  x = x + delta;\
  delta = 0;\
}\
func main() {\
  x = 10;\
  delta = 1;\
  foo(x, delta);\
  print(x);     /* prints 11 */\
  print(delta); /* prints 1 */\
}'
    interpreter = Interpreter()
    interpreter.run(program)
if __name__ == '__main__':
    main()