from tabulate import tabulate
import json

def format_list_dicts(dicts: list[dict], output_format: str = "table"):
    if output_format == "table":
        return tabulate(dicts, headers="keys")

    elif output_format == "json":
        return json.dumps(dicts, indent=2)

    elif output_format == "list":
        output = "-------------\n"
        for i in dicts:
            t = []
            for key in i:
                t.append([str(key), str(i[key])])
            output = output + tabulate(t) + "-------------\n"

    else:
        raise ValueError("Unsupported format type.")






